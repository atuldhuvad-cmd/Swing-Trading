"""CORS and cross-site write policy: only the local Vite dev server origins are allowed."""
import pytest

from tests.pdf_factory import make_pdf
from app.services import broker_upload_service as uploads

ALLOWED = ["http://127.0.0.1:5173", "http://localhost:5173"]
BLOCKED = ["https://attacker.example", "http://localhost:3000", "http://127.0.0.1:5174", "null"]


@pytest.fixture
def no_uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(uploads, "MANIFEST_PATH", tmp_path / "uploads" / "manifest.json")
    monkeypatch.setattr(uploads, "BASE_DIR", tmp_path)


def _preflight(client, origin):
    return client.options("/api/broker-uploads/preview", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST"})


@pytest.mark.parametrize("origin", ALLOWED)
def test_allowed_origin_preflight_and_get(client, origin):
    pre = _preflight(client, origin)
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in pre.headers
    resp = client.get("/health", headers={"Origin": origin})
    assert resp.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", BLOCKED)
def test_blocked_origin_gets_no_cors_headers(client, origin):
    pre = _preflight(client, origin)
    assert "access-control-allow-origin" not in pre.headers
    resp = client.get("/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.parametrize("origin", BLOCKED)
def test_blocked_origin_cannot_run_pdf_endpoints(client, no_uploads, origin):
    # A cross-site multipart POST needs no preflight, so it is refused before it runs.
    pdf = ("r.pdf", make_pdf([["synthetic"]]), "application/pdf")
    preview = client.post("/api/broker-uploads/preview", headers={"Origin": origin}, files={"file": pdf})
    upload = client.post("/api/broker-uploads", headers={"Origin": origin},
                         data={"broker_name": "Broker"}, files={"file": pdf})
    assert preview.status_code == 403 and upload.status_code == 403
    assert not uploads.UPLOAD_DIR.exists()  # nothing stored


@pytest.mark.parametrize("origin", ALLOWED + [None])
def test_allowed_origin_or_same_origin_proxy_request_is_served(client, no_uploads, origin):
    headers = {"Origin": origin} if origin else {}
    resp = client.post("/api/broker-uploads", headers=headers, data={"broker_name": "Broker"},
                       files={"file": ("r.pdf", make_pdf([["synthetic"]]), "application/pdf")})
    assert resp.status_code == 200
