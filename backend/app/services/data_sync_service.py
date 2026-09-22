"""In-app trigger for the on-demand scratch/auto_download_*.py scripts.

This does not reimplement those scripts -- it shells out to the exact same
files you already run by hand from a terminal (scratch/auto_download_ohlcv.py,
scratch/auto_download_fundamentals.py, scratch/auto_download_broker_recs_icici.py),
using the same Python interpreter that is running this backend (sys.executable),
so it always has the same dependencies (pandas, lxml, requests, SQLAlchemy)
already proven to import correctly. Nothing about what each script does or
writes changes because it was triggered from the UI instead of a terminal --
the OHLCV job still backs up the production DB before importing; the
fundamentals and ICICI-recs jobs still only download and report, never write
to the database.

Each job's own script already writes a timestamped JSON report to its own
output folder -- this module's only job is to run the right script with the
right flags, and locate/read back the newest such report afterwards.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from app.config import BASE_DIR

SCRATCH_DIR = BASE_DIR / "scratch"
DEFAULT_TIMEOUT_SECONDS = 900  # generous: NSE/ICICI fetches can be slow


class DataSyncJob:
    def __init__(self, job_id: str, label: str, script: str, out_dir: Path,
                 report_glob: str, writes_db: bool, default_args: list[str],
                 summarize) -> None:
        self.job_id = job_id
        self.label = label
        self.script_path = SCRATCH_DIR / script
        self.out_dir = out_dir
        self.report_glob = report_glob
        self.writes_db = writes_db
        self.default_args = default_args
        self._summarize = summarize

    def latest_report(self) -> dict[str, Any] | None:
        if not self.out_dir.exists():
            return None
        candidates = sorted(self.out_dir.glob(self.report_glob), key=lambda p: p.stat().st_mtime)
        if not candidates:
            return None
        path = candidates[-1]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return {"report_path": str(path), "mtime": path.stat().st_mtime, "summary": self._summarize(data)}


def _summarize_ohlcv(data: dict) -> dict:
    results = data.get("results", [])
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.get("status", "UNKNOWN")] = by_status.get(r.get("status", "UNKNOWN"), 0) + 1
    return {
        "generated_at": data.get("generated_at"),
        "dry_run": data.get("dry_run"),
        "database_scope": "production" if data.get("production_database") else "non-production",
        "total_items": len(results),
        "by_status": by_status,
    }


def _summarize_fundamentals(data: dict) -> dict:
    results = data.get("results", [])
    total_new = sum(len(r.get("new_filings", [])) for r in results)
    total_covered = sum(len(r.get("already_covered", [])) for r in results)
    failures = [r.get("symbol") for r in results if r.get("status") == "FETCH_FAILED"]
    return {
        "generated_at": data.get("generated_at"),
        "lookback_days": data.get("lookback_days"),
        "symbols_checked": len(results),
        "new_filings": total_new,
        "already_covered": total_covered,
        "fetch_failures": failures,
    }


def _summarize_broker_recs(data: dict) -> dict:
    return {
        "generated_at": data.get("generated_at"),
        "status": data.get("status", "UNKNOWN"),
        "error": data.get("error"),
        "total_rows": data.get("total_rows"),
        "actionable": len(data.get("actionable", [])),
        "already_recorded": len(data.get("already_recorded", [])),
        "unmatched_or_untracked": len(data.get("unmatched_or_untracked", [])),
    }


JOBS: dict[str, DataSyncJob] = {
    "ohlcv": DataSyncJob(
        job_id="ohlcv",
        label="NSE OHLCV + Bhavcopy",
        script="auto_download_ohlcv.py",
        out_dir=BASE_DIR / "manual_inputs" / "nse" / "auto",
        report_glob="auto_download_report_*.json",
        writes_db=True,
        default_args=[],
        summarize=_summarize_ohlcv,
    ),
    "fundamentals": DataSyncJob(
        job_id="fundamentals",
        label="Quarterly fundamentals filings",
        script="auto_download_fundamentals.py",
        out_dir=BASE_DIR / "manual_inputs" / "fundamentals" / "filings",
        report_glob="auto_download_report_*.json",
        writes_db=False,
        default_args=[],
        summarize=_summarize_fundamentals,
    ),
    "broker_recs_icici": DataSyncJob(
        job_id="broker_recs_icici",
        label="ICICI Direct broker recommendations",
        script="auto_download_broker_recs_icici.py",
        out_dir=BASE_DIR / "manual_inputs" / "broker_recommendations",
        report_glob="icici_report_*.json",
        writes_db=False,
        default_args=[],
        summarize=_summarize_broker_recs,
    ),
}


class DataSyncError(Exception):
    pass


class DataSyncBusyError(DataSyncError):
    pass


_RUN_LOCKS = {job_id: threading.Lock() for job_id in JOBS}


def list_jobs() -> list[dict[str, Any]]:
    out = []
    for job in JOBS.values():
        out.append({
            "job_id": job.job_id,
            "label": job.label,
            "writes_db": job.writes_db,
            "script_exists": job.script_path.exists(),
            "last_report": job.latest_report(),
        })
    return out


def run_job(job_id: str, extra_args: list[str] | None = None,
            timeout: int = DEFAULT_TIMEOUT_SECONDS,
            confirm_production: bool = False) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise DataSyncError(f"Unknown job '{job_id}'")
    if not job.script_path.exists():
        raise DataSyncError(f"Script not found: {job.script_path}")
    if job.writes_db and not confirm_production:
        raise DataSyncError("Explicit production-import confirmation is required")

    run_lock = _RUN_LOCKS[job_id]
    if not run_lock.acquire(blocking=False):
        raise DataSyncBusyError(f"Job '{job_id}' is already running")

    try:
        before_mtime = None
        before = job.latest_report()
        if before:
            before_mtime = before["mtime"]

        effective_args = [*job.default_args, *(extra_args or [])]
        if job.writes_db and confirm_production and "--confirm-production" not in effective_args:
            effective_args.append("--confirm-production")
        cmd = [sys.executable, str(job.script_path), *effective_args]
        started = time.time()
        try:
            proc = subprocess.run(
                cmd, cwd=str(SCRATCH_DIR), capture_output=True, text=True, timeout=timeout,
            )
            timed_out = False
            returncode = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            returncode = None
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else (e.stderr or b"").decode("utf-8", "replace")
        duration = round(time.time() - started, 1)

        after = job.latest_report()
        new_report = after if (after and after["mtime"] != before_mtime) else None

        # Trim to keep the HTTP response reasonable; the full files stay on disk.
        def tail(s: str, n: int = 4000) -> str:
            return s if len(s) <= n else "...(truncated)...\n" + s[-n:]

        return {
            "job_id": job_id,
            "label": job.label,
            "writes_db": job.writes_db,
            "timed_out": timed_out,
            "returncode": returncode,
            "duration_seconds": duration,
            "stdout_tail": tail(stdout),
            "stderr_tail": tail(stderr),
            "report": new_report,
        }
    finally:
        run_lock.release()
