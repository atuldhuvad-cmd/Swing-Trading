"""Manual PDF storage for broker recommendation reports.

This does NOT scrape or parse anything -- it exists because ICICI Direct's
public page is the only broker recommendation source this project could
reliably auto-download (see scratch/auto_download_broker_recs_icici.py).
Every other brokerage either requires a login to see real recommendations
(HDFC Securities, Kotak) or has no genuine public page at all. Rather than
build scrapers on top of sites that may or may not actually work, this gives
you a place to upload a PDF report you already have (Motilal Oswal,
Sharekhan, 5paisa, or anything else) and keep it next to your other broker
research, so you can enter the actual facts through the existing "Enter a
recommendation" screen (/recommendations/new) -- same as your original 5
ICICI entries. Nothing here writes to the production database.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import BASE_DIR

UPLOAD_DIR = BASE_DIR / "manual_inputs" / "broker_recommendations" / "uploads"
MANIFEST_PATH = UPLOAD_DIR / "manifest.json"

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB -- generous for a broker PDF report
ALLOWED_CONTENT_TYPES = {"application/pdf"}


class BrokerUploadError(Exception):
    """Raised for a bad request (validation) -- the router maps this to HTTP 400."""


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


def _read_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return []
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BrokerUploadError("Upload index could not be read; existing reports were preserved") from exc


def _write_manifest(entries: list[dict[str, Any]]) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


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


def save_upload(
    *,
    broker_name: str,
    original_filename: str,
    content: bytes,
    content_type: str | None,
    stock_symbol: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    broker_name = (broker_name or "").strip()
    if not broker_name:
        raise BrokerUploadError("Broker name is required")

    safe_name = _safe_filename(original_filename)
    if not safe_name.lower().endswith(".pdf"):
        raise BrokerUploadError("Only .pdf files are supported")
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise BrokerUploadError(f"Unsupported file type: {content_type} (expected application/pdf)")
    if not content:
        raise BrokerUploadError("File is empty")
    if not content.startswith(b"%PDF-"):
        raise BrokerUploadError("File content is not a valid PDF")
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise BrokerUploadError(
            f"File is too large ({len(content) / 1_048_576:.1f} MB) -- limit is "
            f"{MAX_FILE_SIZE_BYTES / 1_048_576:.0f} MB"
        )

    entries = _read_manifest()
    now = datetime.now(timezone.utc)
    upload_id = f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    broker_dir = UPLOAD_DIR / _slugify(broker_name, fallback="broker")
    broker_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{upload_id}_{safe_name}"
    stored_full_path = broker_dir / stored_name
    stored_full_path.write_bytes(content)

    entry = {
        "upload_id": upload_id,
        "broker_name": broker_name,
        "stock_symbol": (stock_symbol or "").strip() or None,
        "note": (note or "").strip() or None,
        "original_filename": safe_name,
        "stored_path": str(stored_full_path.relative_to(BASE_DIR)).replace("\\", "/"),
        "size_bytes": len(content),
        "uploaded_at": now.isoformat(),
    }

    entries.append(entry)
    _write_manifest(entries)
    return entry
