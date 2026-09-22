import pytest
from app.services import broker_upload_service as svc


def _pdf_bytes(size: int = 1024) -> bytes:
    # Minimal content -- the service only checks extension/content-type/size,
    # it never parses the PDF itself, so this doesn't need to be a valid PDF.
    return b"%PDF-1.4\n" + b"0" * size


def _patch_dirs(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(svc, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(svc, "MANIFEST_PATH", upload_dir / "manifest.json")
    monkeypatch.setattr(svc, "BASE_DIR", tmp_path)
    return upload_dir


def test_upload_and_list(client, monkeypatch, tmp_path):
    upload_dir = _patch_dirs(monkeypatch, tmp_path)

    resp = client.post(
        "/api/broker-uploads",
        data={"broker_name": "Motilal Oswal", "stock_symbol": "RELIANCE", "note": "Q2 pick"},
        files={"file": ("motilal_reco.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["broker_name"] == "Motilal Oswal"
    assert body["stock_symbol"] == "RELIANCE"
    assert body["note"] == "Q2 pick"
    assert body["original_filename"] == "motilal_reco.pdf"

    listed = client.get("/api/broker-uploads").json()
    assert len(listed) == 1
    assert listed[0]["upload_id"] == body["upload_id"]

    stored = upload_dir / "motilal_oswal"
    assert stored.exists()
    assert len(list(stored.iterdir())) == 1


def test_upload_rejects_non_pdf(client, monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    resp = client.post(
        "/api/broker-uploads",
        data={"broker_name": "Sharekhan"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_rejects_fake_pdf_content(client, monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    resp = client.post(
        "/api/broker-uploads",
        data={"broker_name": "Sharekhan"},
        files={"file": ("notes.pdf", b"not really a pdf", "application/pdf")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "File content is not a valid PDF"


def test_upload_rejects_missing_broker_name(client, monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    resp = client.post(
        "/api/broker-uploads",
        data={"broker_name": "   "},
        files={"file": ("reco.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 400


def test_download_uploaded_file(client, monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)

    resp = client.post(
        "/api/broker-uploads",
        data={"broker_name": "5paisa"},
        files={"file": ("picks.pdf", _pdf_bytes(2048), "application/pdf")},
    )
    upload_id = resp.json()["upload_id"]

    file_resp = client.get(f"/api/broker-uploads/{upload_id}/file")
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] == "application/pdf"
    assert file_resp.content.startswith(b"%PDF-1.4")


def test_download_missing_upload_404(client, monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    resp = client.get("/api/broker-uploads/does-not-exist/file")
    assert resp.status_code == 404


def test_corrupt_index_is_preserved(monkeypatch, tmp_path):
    directory = _patch_dirs(monkeypatch, tmp_path)
    directory.mkdir()
    svc.MANIFEST_PATH.write_text("broken-json")
    with pytest.raises(svc.BrokerUploadError):
        svc.save_upload(broker_name="Broker", original_filename="report.pdf",
                        content=_pdf_bytes(), content_type="application/pdf")
    assert svc.MANIFEST_PATH.read_text() == "broken-json"
    assert list(directory.iterdir()) == [svc.MANIFEST_PATH]


def test_download_cannot_escape_upload_directory(monkeypatch, tmp_path):
    _patch_dirs(monkeypatch, tmp_path)
    with pytest.raises(svc.BrokerUploadError):
        svc.resolve_file_path({"stored_path": "../outside.pdf"})
