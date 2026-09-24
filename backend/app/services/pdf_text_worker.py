"""Isolated PDF text reader, run as a separate process for untrusted PDFs.

Usage: python -I pdf_text_worker.py <max_pages> <max_text_chars>

The PDF bytes arrive on stdin; one JSON object is written to stdout:
  {"ok": true, "encrypted": bool, "pages": [...], "page_limit_reached": bool}
  {"ok": false, "error": "UNREADABLE" | "TEXT_LIMIT"}

It imports only the standard library and pypdf (never the application), so a
pathological file can be killed by the parent without touching app state.
Nothing is written to disk. Error details never leave this process.
"""
import io
import json
import sys


def _limit_memory() -> None:
    try:  # POSIX only; on Windows the parent's timeout is the bound
        import resource
        limit = 1024 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except Exception:  # noqa: BLE001
        pass


def read(content: bytes, max_pages: int, max_chars: int) -> dict:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            try:
                encrypted = reader.decrypt("") == 0
            except Exception:  # noqa: BLE001 - any failure means we cannot read it
                encrypted = True
        if encrypted:
            return {"ok": True, "encrypted": True, "pages": [], "page_limit_reached": False}
        pages, total, limit_reached = [], 0, False
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                limit_reached = True
                break
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 - a broken page must not abort the preview
                text = ""
            total += len(text)
            if total > max_chars:
                return {"ok": False, "error": "TEXT_LIMIT"}
            pages.append(text)
        return {"ok": True, "encrypted": False, "pages": pages, "page_limit_reached": limit_reached}
    except MemoryError:
        return {"ok": False, "error": "TEXT_LIMIT"}
    except Exception:  # noqa: BLE001 - malformed PDFs raise many exception types
        return {"ok": False, "error": "UNREADABLE"}


def main() -> int:
    max_pages, max_chars = int(sys.argv[1]), int(sys.argv[2])
    _limit_memory()
    content = sys.stdin.buffer.read()
    result = read(content, max_pages, max_chars)
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
