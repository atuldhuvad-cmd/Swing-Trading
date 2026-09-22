import json
import subprocess

from app.services import data_sync_service as svc


def test_list_jobs_shape(client):
    resp = client.get("/api/data-sync/jobs")
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    ids = {j["job_id"] for j in jobs}
    assert ids == {"ohlcv", "fundamentals", "broker_recs_icici"}
    by_id = {j["job_id"]: j for j in jobs}
    assert by_id["ohlcv"]["writes_db"] is True
    assert by_id["fundamentals"]["writes_db"] is False
    assert by_id["broker_recs_icici"]["writes_db"] is False
    for j in jobs:
        assert j["script_exists"] is True, f"{j['job_id']} script missing on disk"


def test_run_unknown_job_404(client):
    resp = client.post("/api/data-sync/jobs/not-a-real-job/run")
    assert resp.status_code == 404


def test_production_job_requires_confirmation(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unconfirmed request must never launch the job")
    monkeypatch.setattr(svc, "run_job", forbidden)
    assert client.post("/api/data-sync/jobs/ohlcv/run").status_code == 409


def test_confirmed_production_job_passes_script_confirmation(client, monkeypatch, tmp_path):
    job = svc.JOBS["ohlcv"]
    fake_out_dir = tmp_path / "ohlcv_out"
    fake_out_dir.mkdir()
    monkeypatch.setattr(job, "out_dir", fake_out_dir, raising=False)
    captured = {}

    def fake_run(cmd, cwd, capture_output, text, timeout):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(svc.subprocess, "run", fake_run)
    resp = client.post("/api/data-sync/jobs/ohlcv/run", json={"confirm_production": True})
    assert resp.status_code == 200
    assert "--confirm-production" in captured["cmd"]


def test_duplicate_job_run_is_rejected(client):
    lock = svc._RUN_LOCKS["fundamentals"]
    assert lock.acquire(blocking=False)
    try:
        resp = client.post("/api/data-sync/jobs/fundamentals/run")
        assert resp.status_code == 409
        assert "already running" in resp.json()["detail"]
    finally:
        lock.release()


def test_run_job_success_reads_new_report(client, monkeypatch, tmp_path):
    job = svc.JOBS["fundamentals"]
    fake_out_dir = tmp_path / "fundamentals_out"
    fake_out_dir.mkdir()
    monkeypatch.setattr(job, "out_dir", fake_out_dir, raising=False)

    def fake_run(cmd, cwd, capture_output, text, timeout):
        # Simulate the real script's own behavior: it writes its own
        # timestamped report file as a side effect, then exits 0.
        report = {
            "generated_at": "20260101_000000",
            "lookback_days": 120,
            "results": [
                {"symbol": "BEL", "status": "OK", "new_filings": [{"an_dt": "x"}], "already_covered": []},
            ],
        }
        (fake_out_dir / "auto_download_report_20260101_000000.json").write_text(json.dumps(report))
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(svc.subprocess, "run", fake_run)

    resp = client.post("/api/data-sync/jobs/fundamentals/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["returncode"] == 0
    assert body["timed_out"] is False
    assert body["report"] is not None
    assert body["report"]["summary"]["new_filings"] == 1
    assert body["report"]["summary"]["symbols_checked"] == 1


def test_run_job_timeout_reports_gracefully(client, monkeypatch, tmp_path):
    job = svc.JOBS["broker_recs_icici"]
    fake_out_dir = tmp_path / "broker_recs_out"
    fake_out_dir.mkdir()
    monkeypatch.setattr(job, "out_dir", fake_out_dir, raising=False)

    def fake_run(cmd, cwd, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(cmd, timeout, output="partial", stderr="")

    monkeypatch.setattr(svc.subprocess, "run", fake_run)

    resp = client.post("/api/data-sync/jobs/broker_recs_icici/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["timed_out"] is True
    assert body["returncode"] is None
    assert body["report"] is None
