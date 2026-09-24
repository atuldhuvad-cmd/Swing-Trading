"""Manual PDF storage for broker recommendation reports.

This does NOT scrape anything. It keeps broker-authored report PDFs you
already have (for example Motilal Oswal, ICICI Securities or Axis Securities
reports found through Trendlyne) next to your other broker research, so the
facts can be verified and entered through the recommendation workflow.
Nothing here writes to the production database.

Every stored file records its SHA-256; a byte-identical file is refused as a
duplicate (DUPLICATE_FILE) so the same report is stored only once. Entries
written before SHA-256 was recorded stay valid: their hash is computed from
the stored file when needed and the manifest is not rewritten.

Discovery provenance (for example "Trendlyne" plus the page URL, when it is
known) is kept separate from the broker, which is the report's author.

The manifest is only ever replaced atomically (temporary file in the same
directory, flush + fsync, ``os.replace``), so a reader sees the old or the new
index, never a partial one. The whole read-check-write of an upload runs under
an in-process lock and a cross-process file lock, so concurrent uploads cannot
lose entries or store the same PDF twice.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import BASE_DIR

UPLOAD_DIR = BASE_DIR / "manual_inputs" / "broker_recommendations" / "uploads"
MANIFEST_PATH = UPLOAD_DIR / "manifest.json"

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB -- generous for a broker PDF report
ALLOWED_CONTENT_TYPES = {"application/pdf"}
MAX_DISCOVERY_SOURCE_LEN = 100
MAX_DISCOVERY_URL_LEN = 1000
LOCK_TIMEOUT_SECONDS = 30.0
_REPLACE_RETRY_SECONDS = 2.0   # Windows: a reader may briefly hold the manifest open

_THREAD_LOCK = threading.RLock()


class BrokerUploadError(Exception):
    """Raised for a bad request (validation) -- the router maps this to HTTP 400."""


class UploadStorageError(BrokerUploadError):
    """The report or index could not be saved -- the router maps this to HTTP 500."""


class DuplicateUploadError(BrokerUploadError):
    """A byte-identical PDF is already stored -- the router maps this to HTTP 409."""

    def __init__(self, existing: dict[str, Any]):
        super().__init__(f"DUPLICATE_FILE: identical PDF already stored as upload {existing.get('upload_id')}")
        self.existing = existing


def _slugify(text: str, fallback: str = "unknown") -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or fallback


def _safe_filename(filename: str) -> str:
    # Keep only the basename (no directory components -- blocks path
    # traversal) and strip anything that isn't a safe filename character.
    name = Path(filename or "upload.pdf").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "upload.pdf"


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_pdf(original_filename: str, content: bytes, content_type: str | None) -> str:
    """Check a candidate PDF before it is previewed or stored; returns the safe filename."""
    safe_name = _safe_filename(original_filename)
    if not safe_name.lower().endswith(".pdf"):
        raise BrokerUploadError("Only .pdf files are supported")
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise BrokerUploadError(f"Unsupported file type: {content_type} (expected application/pdf)")
    if not content:
        raise BrokerUploadError("File is empty")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise BrokerUploadError(
            f"File is too large ({len(content) / 1_048_576:.1f} MB) -- limit is "
            f"{MAX_FILE_SIZE_BYTES / 1_048_576:.0f} MB"
        )
    if not content.startswith(b"%PDF-"):
        raise BrokerUploadError("File content is not a valid PDF")
    return safe_name


def validate_discovery(discovery_source: str | None, discovery_url: str | None) -> tuple[str | None, str | None]:
    source = (discovery_source or "").strip() or None
    url = (discovery_url or "").strip() or None
    if source and len(source) > MAX_DISCOVERY_SOURCE_LEN:
        raise BrokerUploadError("Discovery source is too long")
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or len(url) > MAX_DISCOVERY_URL_LEN:
            raise BrokerUploadError("Discovery URL must be a full http(s) URL")
    return source, url


def _read_manifest() -> list[dict[str, Any]]:
    # Lock-free: the manifest is only ever replaced atomically. On Windows a
    # concurrent os.replace can briefly deny access, so retry for a moment.
    deadline = time.monotonic() + _REPLACE_RETRY_SECONDS
    while True:
        if not MANIFEST_PATH.exists():
            return []
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except PermissionError as exc:
            if time.monotonic() >= deadline:
                raise BrokerUploadError("Upload index could not be read; existing reports were preserved") from exc
            time.sleep(0.02)
        except (json.JSONDecodeError, OSError) as exc:
            raise BrokerUploadError("Upload index could not be read; existing reports were preserved") from exc


def _lock_file(fh) -> None:
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    if os.name == "nt":
        import msvcrt
        while True:
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise UploadStorageError("Upload index is busy; try again shortly") from None
                time.sleep(0.05)
    import fcntl
    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise UploadStorageError("Upload index is busy; try again shortly") from None
            time.sleep(0.05)


def _unlock_file(fh) -> None:
    if os.name == "nt":
        import msvcrt
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _manifest_lock():
    """Serialise manifest writers across threads and processes."""
    with _THREAD_LOCK:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        with open(UPLOAD_DIR / ".manifest.lock", "a+b") as fh:
            _lock_file(fh)
            try:
                yield
            finally:
                _unlock_file(fh)


def _write_manifest(entries: list[dict[str, Any]]) -> None:
    """Atomically replace the manifest; the previous one survives any failure."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".manifest.", suffix=".tmp", dir=UPLOAD_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(entries, indent=2))
            fh.flush()
            os.fsync(fh.fileno())
        deadline = time.monotonic() + _REPLACE_RETRY_SECONDS
        while True:
            try:
                os.replace(tmp, MANIFEST_PATH)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def list_uploads() -> list[dict[str, Any]]:
    entries = _read_manifest()
    return sorted(entries, key=lambda e: e.get("uploaded_at", ""), reverse=True)


def get_upload(upload_id: str) -> dict[str, Any] | None:
    for entry in _read_manifest():
        if entry.get("upload_id") == upload_id:
            return entry
    return None


def resolve_file_path(entry: dict[str, Any]) -> Path:
    path = (BASE_DIR / entry["stored_path"]).resolve()
    if not path.is_relative_to(UPLOAD_DIR.resolve()):
        raise BrokerUploadError("Stored file path is outside the upload directory")
    return path


def entry_sha256(entry: dict[str, Any]) -> str | None:
    """SHA-256 of a stored upload; computed from the file for entries that predate it."""
    if entry.get("sha256"):
        return entry["sha256"]
    try:
        path = resolve_file_path(entry)
        return sha256_hex(path.read_bytes()) if path.exists() else None
    except (BrokerUploadError, KeyError, OSError):
        return None


def find_by_sha256(sha: str) -> dict[str, Any] | None:
    """Read-only lookup of an already-stored, byte-identical PDF."""
    for entry in _read_manifest():
        if entry_sha256(entry) == sha:
            return entry
    return None


def save_upload(
    *,
    broker_name: str,
    original_filename: str,
    content: bytes,
    content_type: str | None,
    stock_symbol: str | None = None,
    note: str | None = None,
    discovery_source: str | None = None,
    discovery_url: str | None = None,
) -> dict[str, Any]:
    broker_name = (broker_name or "").strip()
    if not broker_name:
        raise BrokerUploadError("Broker name is required")
    safe_name = validate_pdf(original_filename, content, content_type)
    source, url = validate_discovery(discovery_source, discovery_url)

    sha = sha256_hex(content)
    with _manifest_lock():
        entries = _read_manifest()
        for existing in entries:
            if entry_sha256(existing) == sha:
                raise DuplicateUploadError(existing)

        now = datetime.now(timezone.utc)
        upload_id = f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        broker_dir = UPLOAD_DIR / _slugify(broker_name, fallback="broker")
        stored_full_path = broker_dir / f"{upload_id}_{safe_name}"
        entry = {
            "upload_id": upload_id,
            "broker_name": broker_name,
            "stock_symbol": (stock_symbol or "").strip() or None,
            "note": (note or "").strip() or None,
            "original_filename": safe_name,
            "stored_path": str(stored_full_path.relative_to(BASE_DIR)).replace("\\", "/"),
            "size_bytes": len(content),
            "uploaded_at": now.isoformat(),
            "sha256": sha,
            "discovery_source": source,
            "discovery_url": url,
        }
        created = False
        try:
            broker_dir.mkdir(parents=True, exist_ok=True)
            with open(stored_full_path, "xb") as fh:  # never overwrites an existing file
                created = True
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            if created:  # remove only a file this call created
                with contextlib.suppress(OSError):
                    stored_full_path.unlink()
            raise UploadStorageError("The report could not be saved; nothing was stored") from exc
        try:
            _write_manifest(entries + [entry])
        except OSError as exc:
            with contextlib.suppress(OSError):
                stored_full_path.unlink()
            raise UploadStorageError("Upload index could not be saved; the report was not stored") from exc
    return entry
