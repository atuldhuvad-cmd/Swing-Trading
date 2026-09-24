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


# ---------------------------------------------------------------- CORS_ALLOWED_ORIGINS validation

import os
import subprocess
import sys
from pathlib import Path

from app.config import Settings, validate_origin

VALID_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173", "https://localhost", "http://192.168.1.20:5173",
                 "http://[::1]:5173", "http://my-pc.local:5173"]
INVALID_ORIGINS = ["*", "null", "", " ", " http://localhost:5173", "http://localhost:5173/", "http://localhost:5173/app",
                   "http://*.example.com", "https://*", "ftp://localhost:5173", "file:///tmp", "localhost:5173",
                   "http://", "http://localhost:0", "http://localhost:70000", "http://localhost:abc",
                   "http://256.1.1.1:5173", "http://LOCALHOST:5173", "HTTP://localhost:5173", "http://user@localhost:5173",
                   "http://localhost:5173?x=1", "http://localhost:5173#f", "http://-bad-.example", "http://a_b.example",
                   "javascript:alert(1)"]


def test_defaults_are_the_two_vite_origins():
    assert Settings().cors_allowed_origins == ["http://127.0.0.1:5173", "http://localhost:5173"]


@pytest.mark.parametrize("origin", VALID_ORIGINS)
def test_valid_origins_are_accepted(origin):
    assert validate_origin(origin) == origin


@pytest.mark.parametrize("origin", INVALID_ORIGINS)
def test_invalid_origins_are_rejected(origin):
    with pytest.raises(ValueError):
        validate_origin(origin)


@pytest.mark.parametrize("value", ['["*"]', '["null"]', '["http://localhost:5173/"]', '[""]', "not-json",
                                   '"http://localhost:5173"', '["http://*.example.com"]'])
def test_bad_configuration_fails_closed_with_a_concise_message(value, tmp_path):
    backend = Path(__file__).resolve().parent.parent
    env = dict(os.environ, CORS_ALLOWED_ORIGINS=value, DATABASE_URL=f"sqlite:///{tmp_path / 'unused.db'}")
    result = subprocess.run([sys.executable, "-c", "import app.main"], cwd=str(backend), env=env,
                            capture_output=True, text=True)
    assert result.returncode != 0
    message = result.stderr.strip()
    assert message.startswith("Invalid configuration") and "\n" not in message and "Traceback" not in message


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize("origin", ["https://attacker.example", "null", "", "http://localhost:5173/", "HTTP://LOCALHOST:5173"])
def test_every_write_method_from_a_foreign_or_malformed_origin_is_refused(client, method, origin):
    resp = getattr(client, method)("/api/imports/1/rollback" if method == "post" else "/api/recommendations/1",
                                   headers={"Origin": origin})
    assert resp.status_code == 403
