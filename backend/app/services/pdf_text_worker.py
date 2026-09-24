"""Isolated PDF text reader, run as a separate process for untrusted PDFs.

Usage: python -I -S pdf_text_worker.py <max_pages> <max_text_chars> <memory_limit_bytes> <site_packages_dir>

The PDF bytes arrive on stdin; one JSON object is written to stdout:
  {"ok": true, "encrypted": bool, "pages": [...], "page_limit_reached": bool}
  {"ok": false, "error": "UNREADABLE" | "RESOURCE_LIMIT" | "WORKER"}

It imports only the standard library and pypdf (never the application), so a
pathological file can be killed by the parent without touching app state.
Nothing is written to disk. Error details never leave this process.

Memory: on POSIX the address space is capped here; on Windows the parent puts
this process in a Job Object with a process memory limit before sending the PDF.
Nothing heavy happens until the PDF arrives on stdin, so the limit is in place
before parsing starts.
"""
import io
import json
import sys


def _limit_memory(limit: int) -> None:
    try:  # POSIX only; on Windows the parent's Job Object applies the limit
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except Exception:  # noqa: BLE001
        pass


def read(content: bytes, max_pages: int, max_chars: int) -> dict:
    try:
        from pypdf import PdfReader
    except Exception:  # noqa: BLE001 - the worker environment is broken, not the PDF
        return {"ok": False, "error": "WORKER"}

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            try:
                encrypted = reader.decrypt("") == 0
            except MemoryError:
                raise
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
            except MemoryError:
                raise  # a resource limit, never an empty page
            except Exception:  # noqa: BLE001 - a broken page must not abort the preview
                text = ""
            total += len(text)
            if total > max_chars:
                return {"ok": False, "error": "RESOURCE_LIMIT"}
            pages.append(text)
        return {"ok": True, "encrypted": False, "pages": pages, "page_limit_reached": limit_reached}
    except MemoryError:
        return {"ok": False, "error": "RESOURCE_LIMIT"}
    except Exception:  # noqa: BLE001 - malformed PDFs raise many exception types
        return {"ok": False, "error": "UNREADABLE"}


def main() -> int:
    max_pages, max_chars, memory_limit = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    if len(sys.argv) > 4:
        # Appended after the standard library, so nothing in the venv folder can
        # shadow a standard-library module; -I -S load no other site-packages.
        sys.path.append(sys.argv[4])
    _limit_memory(memory_limit)
    content = sys.stdin.buffer.read()
    try:
        result = read(content, max_pages, max_chars)
    except MemoryError:
        result = {"ok": False, "error": "RESOURCE_LIMIT"}
    del content
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
