"""Untrusted PDFs are parsed in a separate, time-limited, killable process.

All PDFs are synthetic (tests/pdf_factory.py).
"""
import subprocess
import time

import pytest

from app.config import BASE_DIR
from app.services import broker_pdf_extraction as extraction
from app.services import broker_upload_service as uploads
from tests.pdf_factory import make_pdf, make_slow_pdf


@pytest.fixture
def no_uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(uploads, "MANIFEST_PATH", tmp_path / "uploads" / "manifest.json")
    monkeypatch.setattr(uploads, "BASE_DIR", tmp_path)


@pytest.fixture
def spawned(monkeypatch):
    """Record every parser process so tests can prove it was terminated and reaped."""
    procs = []
    real = subprocess.Popen

    def recording(*args, **kwargs):
        p = real(*args, **kwargs)
        procs.append(p)
        return p

    monkeypatch.setattr(extraction.subprocess, "Popen", recording)
    return procs


def _assert_client_safe(detail: str):
    assert "Traceback" not in detail and 'File "' not in detail
    assert str(BASE_DIR) not in detail and "pdf_text_worker" not in detail


def test_isolated_extraction_matches_in_process_extraction(spawned):
    content = make_pdf([["Motilal Oswal Financial Services", "Motilal Oswal research is available",
                         "9 September 2026", "CMP: INR3,105 TP: INR3,880 (+25%) Buy"]])
    iso, local = extraction.extract_fields_isolated(content), extraction.extract_fields(content)
    assert iso.as_dict() == local.as_dict()
    assert len(spawned) == 1 and spawned[0].returncode == 0


def test_pathological_pdf_is_killed_at_the_timeout(monkeypatch, spawned):
    monkeypatch.setattr(extraction, "PARSE_TIMEOUT_SECONDS", 1.0)
    started = time.monotonic()
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_slow_pdf())
    assert time.monotonic() - started < 10
    assert str(exc.value) == extraction.TIMEOUT_MESSAGE
    assert len(spawned) == 1 and spawned[0].returncode is not None  # terminated and reaped


def test_text_limit_is_a_controlled_error(monkeypatch, spawned):
    monkeypatch.setattr(extraction, "MAX_TEXT_CHARS", 50)
    content = make_pdf([["x" * 80]])
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(content)
    assert str(exc.value) == extraction.RESOURCE_LIMIT_MESSAGE and exc.value.category == extraction.RESOURCE_LIMIT
    assert spawned[0].returncode is not None


def test_page_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(extraction, "MAX_PAGES", 3)
    ex = extraction.extract_fields_isolated(make_pdf([[f"page {i}"] for i in range(5)]))
    assert ex.page_count == 3
    assert "PAGE_LIMIT: only the first 3 pages were read" in ex.warnings


def test_unreadable_pdf_is_a_controlled_error(spawned):
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(b"%PDF-1.4\n" + b"0" * 2000)
    assert str(exc.value) == extraction.UNREADABLE_MESSAGE
    assert spawned[0].returncode is not None


def test_crashed_worker_is_a_controlled_error(monkeypatch):
    monkeypatch.setattr(extraction, "_WORKER_PATH", extraction._WORKER_PATH.with_name("missing_worker.py"))
    with pytest.raises(extraction.PdfExtractionError) as exc:
        extraction.extract_fields_isolated(make_pdf([["text"]]))
    assert str(exc.value) == extraction.PARSER_FAILED_MESSAGE and exc.value.category == extraction.PARSER_FAILED
    _assert_client_safe(str(exc.value))


def test_api_timeout_returns_400_without_trace_or_paths(client, no_uploads, monkeypatch):
    monkeypatch.setattr(extraction, "PARSE_TIMEOUT_SECONDS", 1.0)
    resp = client.post("/api/broker-uploads/preview",
                       files={"file": ("slow.pdf", make_slow_pdf(), "application/pdf")})
    assert resp.status_code == 400
    assert resp.json()["detail"] == extraction.TIMEOUT_MESSAGE
    _assert_client_safe(resp.text)


def test_api_unreadable_pdf_returns_400_without_trace_or_paths(client, no_uploads):
    resp = client.post("/api/broker-uploads/preview",
                       files={"file": ("x.pdf", b"%PDF-1.4\n" + b"0" * 2000, "application/pdf")})
    assert resp.status_code == 400 and resp.json()["detail"] == extraction.UNREADABLE_MESSAGE
    _assert_client_safe(resp.text)


def test_api_stays_responsive_while_a_pdf_is_parsed(client, no_uploads, monkeypatch):
    """Both requests share one event loop, as under uvicorn; parsing must not block it."""
    import asyncio

    import httpx

    from app.main import app

    monkeypatch.setattr(extraction, "PARSE_TIMEOUT_SECONDS", 4.0)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=60) as ac:
            slow = asyncio.create_task(ac.post(
                "/api/broker-uploads/preview", files={"file": ("slow.pdf", make_slow_pdf(), "application/pdf")}))
            started = time.monotonic()  # a blocked loop would also delay this sleep
            await asyncio.sleep(0.5)
            quick = await ac.get("/api/broker-uploads")
            elapsed = time.monotonic() - started
            slow_resp = await slow
            return quick, elapsed, slow_resp

    quick, elapsed, slow_resp = asyncio.run(scenario())
    assert quick.status_code == 200 and elapsed < 2.5
    assert slow_resp.status_code == 400 and slow_resp.json()["detail"] == extraction.TIMEOUT_MESSAGE
