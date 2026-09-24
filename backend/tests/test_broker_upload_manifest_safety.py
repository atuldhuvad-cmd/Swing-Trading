"""Manifest safety: locked read-check-write, atomic replacement and cleanup.

Synthetic bytes only; every test works in its own temporary upload directory.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.services import broker_upload_service as svc

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _pdf(tag: str) -> bytes:
    return b"%PDF-1.4\n" + tag.encode() + b"\n" + b"0" * 512


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
    directory = tmp_path / "uploads"
    monkeypatch.setattr(svc, "UPLOAD_DIR", directory)
    monkeypatch.setattr(svc, "MANIFEST_PATH", directory / "manifest.json")
    monkeypatch.setattr(svc, "BASE_DIR", tmp_path)
    return directory


def _stored_pdfs(directory: Path) -> list[Path]:
    return [p for p in directory.rglob("*.pdf")]


def _run_threads(n, target):
    barrier = threading.Barrier(n)
    results, errors = [], []

    def go(i):
        barrier.wait()
        try:
            results.append(target(i))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


def test_concurrent_identical_uploads_store_one_file_and_one_entry(upload_dir):
    content = _pdf("same")
    results, errors = _run_threads(8, lambda i: svc.save_upload(
        broker_name="Broker", original_filename=f"{i}.pdf", content=content, content_type="application/pdf"))
    assert len(results) == 1
    assert len(errors) == 7 and all(isinstance(e, svc.DuplicateUploadError) for e in errors)
    assert len(json.loads(svc.MANIFEST_PATH.read_text(encoding="utf-8"))) == 1
    assert len(_stored_pdfs(upload_dir)) == 1


def test_concurrent_different_uploads_keep_every_entry(upload_dir):
    results, errors = _run_threads(12, lambda i: svc.save_upload(
        broker_name="Broker", original_filename=f"{i}.pdf", content=_pdf(f"doc-{i}"), content_type="application/pdf"))
    assert errors == [] and len(results) == 12
    entries = json.loads(svc.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert {e["upload_id"] for e in entries} == {r["upload_id"] for r in results}
    assert len(_stored_pdfs(upload_dir)) == 12


_CHILD = r"""
import sys, time
from pathlib import Path
from app.services import broker_upload_service as svc
base = Path(sys.argv[1])
svc.BASE_DIR = base
svc.UPLOAD_DIR = base / "uploads"
svc.MANIFEST_PATH = svc.UPLOAD_DIR / "manifest.json"
real_read = svc._read_manifest
def slow_read():  # widen the read-check-write window so unlocked writers would collide
    entries = real_read()
    time.sleep(0.3)
    return entries
svc._read_manifest = slow_read
time.sleep(max(0.0, float(sys.argv[3]) - time.time()))  # all processes start together
try:
    svc.save_upload(broker_name="Broker", original_filename="p.pdf",
                    content=sys.argv[2].encode(), content_type="application/pdf")
    print("STORED")
except svc.DuplicateUploadError:
    print("DUPLICATE")
"""


def _spawn(tmp_path, content: str, start_at: float):
    # The child never opens a database; point it at a throwaway path anyway.
    env = dict(os.environ, PYTHONPATH=str(BACKEND_DIR), DATABASE_URL=f"sqlite:///{tmp_path / 'unused.db'}")
    return subprocess.Popen([sys.executable, "-c", _CHILD, str(tmp_path), content, str(start_at)], cwd=str(BACKEND_DIR),
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_cross_process_identical_uploads_store_once(upload_dir, tmp_path):
    start_at = time.time() + 3
    procs = [_spawn(tmp_path, "%PDF-1.4 same across processes", start_at) for _ in range(4)]
    outputs = [p.communicate(timeout=60) for p in procs]
    assert all(p.returncode == 0 for p in procs), [o[1] for o in outputs]
    assert sorted(o[0].strip() for o in outputs) == ["DUPLICATE"] * 3 + ["STORED"]
    assert len(json.loads(svc.MANIFEST_PATH.read_text(encoding="utf-8"))) == 1
    assert len(_stored_pdfs(upload_dir)) == 1


def test_cross_process_different_uploads_keep_every_entry(upload_dir, tmp_path):
    start_at = time.time() + 3
    procs = [_spawn(tmp_path, f"%PDF-1.4 process {i}", start_at) for i in range(4)]
    outputs = [p.communicate(timeout=60) for p in procs]
    assert all(p.returncode == 0 and o[0].strip() == "STORED" for p, o in zip(procs, outputs)), outputs
    assert len(json.loads(svc.MANIFEST_PATH.read_text(encoding="utf-8"))) == 4


def test_readers_never_see_partial_json(upload_dir):
    stop = threading.Event()
    reader_errors, reads = [], [0]

    def reader():
        while not stop.is_set():
            try:
                svc.list_uploads()
                reads[0] += 1
            except Exception as exc:  # noqa: BLE001
                reader_errors.append(exc)

    readers = [threading.Thread(target=reader) for _ in range(3)]
    for t in readers:
        t.start()
    try:
        for i in range(40):
            svc.save_upload(broker_name="Broker", original_filename=f"{i}.pdf",
                            content=_pdf(f"r-{i}") + b"x" * 20000, content_type="application/pdf")
    finally:
        stop.set()
        for t in readers:
            t.join()
    assert reader_errors == [] and reads[0] > 0
    assert len(svc.list_uploads()) == 40


def test_failed_replacement_keeps_old_manifest_and_removes_new_pdf(upload_dir, monkeypatch):
    first = svc.save_upload(broker_name="Broker", original_filename="a.pdf", content=_pdf("a"),
                            content_type="application/pdf")
    before = svc.MANIFEST_PATH.read_bytes()

    def failing_replace(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(svc.os, "replace", failing_replace)
    with pytest.raises(svc.UploadStorageError):
        svc.save_upload(broker_name="Broker", original_filename="b.pdf", content=_pdf("b"),
                        content_type="application/pdf")
    assert svc.MANIFEST_PATH.read_bytes() == before
    assert [p.name for p in _stored_pdfs(upload_dir)] == [Path(first["stored_path"]).name]
    assert list(upload_dir.glob(".manifest.*.tmp")) == []  # temporary file cleaned up


def test_failed_replacement_is_a_controlled_500(client, upload_dir, monkeypatch):
    monkeypatch.setattr(svc.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("disk")))
    resp = client.post("/api/broker-uploads", data={"broker_name": "Broker"},
                       files={"file": ("r.pdf", _pdf("api"), "application/pdf")})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Upload index could not be saved; the report was not stored"
    assert _stored_pdfs(upload_dir) == []


def test_legacy_manifest_entries_survive_new_uploads(upload_dir):
    upload_dir.mkdir()
    legacy = {"upload_id": "20260903_203319_1efbd821", "broker_name": "Broker", "stock_symbol": None,
              "note": None, "original_filename": "legacy.pdf", "stored_path": "uploads/broker/legacy.pdf",
              "size_bytes": 10, "uploaded_at": "2026-09-03T20:33:19+00:00"}
    svc.MANIFEST_PATH.write_text(json.dumps([legacy]), encoding="utf-8")
    svc.save_upload(broker_name="Broker", original_filename="n.pdf", content=_pdf("new"),
                    content_type="application/pdf")
    entries = json.loads(svc.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert entries[0] == legacy and len(entries) == 2 and "sha256" not in entries[0]
