"""Batch A fundamental production import via FastAPI confirm. No candidate re-eval."""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
INTAKE = ROOT / "manual_inputs" / "fundamentals" / "batch_a_manual_intake.json"
APPROVED = ROOT / "manual_inputs" / "fundamentals" / "batch_a_preview_results.json"
REPORT = ROOT / "manual_inputs" / "fundamentals" / "batch_a_import_report.json"

EXPECTED = {
    "ADANIENT": Decimal("100468.61"),
    "ADANIPORTS": Decimal("38735.77"),
    "APOLLOHOSP": Decimal("25228.50"),
    "ASIANPAINT": Decimal("35583.54"),
    "AXISBANK": Decimal("162211.95"),
    "BAJAJ-AUTO": Decimal("62905.00"),
    "BAJAJFINSV": Decimal("150501.77"),
    "BAJFINANCE": Decimal("81989.50"),
    "BEL": Decimal("27610.11"),
    "BHARTIARTL": Decimal("210972.80"),
}
LINE = {
    "ORDINARY": "Revenue from Operations",
    "BANK": "Total Income",
    "NBFC": "Total Income",
}

TABLES = [
    "fundamental_snapshot",
    "data_import_batch",
    "daily_ohlcv",
    "candidate_evaluation_run",
    "candidate_criterion_result",
    "risk_reward_result",
    "broker_recommendation",
    "source_reference",
]


def counts(conn) -> dict:
    out = {}
    for t in TABLES:
        out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    out["fundamental_manual_batches"] = conn.execute(
        "SELECT COUNT(*) FROM data_import_batch WHERE import_type='FUNDAMENTAL_MANUAL'"
    ).fetchone()[0]
    out["synthetic_ohlcv"] = conn.execute(
        "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
    ).fetchone()[0]
    return out


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "data" / f"swing_trading_backup_{stamp}.db"
    shutil.copy2(DB, backup)

    conn = sqlite3.connect(str(DB))
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    before = counts(conn)
    conn.close()

    if integrity != "ok" or fk or before["daily_ohlcv"] != 2469 or before["synthetic_ohlcv"] != 0:
        raise SystemExit(
            json.dumps({"stop": "baseline integrity differs", "integrity": integrity, "fk": fk, "before": before})
        )
    if before["fundamental_snapshot"] != 0 or before["fundamental_manual_batches"] != 0:
        raise SystemExit(json.dumps({"stop": "fundamentals already present", "before": before}))

    approved = {
        r["symbol"]: r["payload_sha256"]
        for r in json.loads(APPROVED.read_text(encoding="utf-8"))["results"]
    }
    intake = json.loads(INTAKE.read_text(encoding="utf-8"))

    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app

    client = TestClient(app)

    preview_rows = []
    sha_ok = True
    for stock in intake["stocks"]:
        payload = stock["payload"]
        res = client.post("/api/fundamentals/preview", json=payload)
        body = res.json()
        sha = body.get("payload_sha256")
        match = sha == approved[stock["nse_symbol"]]
        if not match:
            sha_ok = False
        preview_rows.append(
            {
                "symbol": stock["nse_symbol"],
                "http": res.status_code,
                "action": body.get("action"),
                "persisted": body.get("persisted"),
                "sha": sha,
                "approved_sha": approved[stock["nse_symbol"]],
                "sha_match": match,
                "errors": body.get("errors") or body.get("detail"),
            }
        )
    preview_actions = [r["action"] for r in preview_rows]
    if (
        not sha_ok
        or any(r["http"] != 200 for r in preview_rows)
        or preview_actions.count("ACCEPTED") != 10
        or any(r["persisted"] is not False for r in preview_rows)
    ):
        REPORT.write_text(
            json.dumps(
                {
                    "backup": str(backup),
                    "before": before,
                    "stop": "preview recheck failed",
                    "preview": preview_rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        raise SystemExit("STOP: preview SHA or action mismatch")

    imported = []
    failed = []
    for stock in intake["stocks"]:
        payload = stock["payload"]
        sha = approved[stock["nse_symbol"]]
        res = client.post(
            "/api/fundamentals/confirm",
            json={"payload_sha256": sha, "payload": payload},
        )
        body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {"raw": res.text}
        row = {
            "symbol": stock["nse_symbol"],
            "http": res.status_code,
            "body": body,
        }
        if res.status_code != 200 or not body.get("persisted"):
            failed.append(row)
            break
        imported.append(row)

    replay = []
    if not failed:
        for stock in intake["stocks"]:
            payload = stock["payload"]
            sha = approved[stock["nse_symbol"]]
            res = client.post(
                "/api/fundamentals/confirm",
                json={"payload_sha256": sha, "payload": payload},
            )
            replay.append({"symbol": stock["nse_symbol"], "http": res.status_code, "body": res.json()})

    conn = sqlite3.connect(str(DB))
    after = counts(conn)
    stored = []
    for stock in intake["stocks"]:
        sym = stock["nse_symbol"]
        q = """
        SELECT s.nse_symbol, fs.entity_type, fs.financial_period, fs.period_type, fs.as_of_date,
               fs.version, fs.is_superseded, fs.captured_at, fs.snapshot_id,
               fm.metric_name, fm.metric_value, fm.status,
               sr.publication_name, sr.url, dib.file_sha256, dib.import_batch_id, dib.notes
        FROM fundamental_snapshot fs
        JOIN stock_master s ON s.stock_id = fs.stock_id
        JOIN fundamental_metric fm ON fm.snapshot_id = fs.snapshot_id AND fm.metric_name='revenue'
        LEFT JOIN source_reference sr ON sr.source_reference_id = fs.source_reference_id
        LEFT JOIN data_import_batch dib ON dib.file_sha256 = ?
        WHERE s.nse_symbol = ?
        ORDER BY fs.snapshot_id
        """
        sha = approved[sym]
        rows = conn.execute(q, (sha, sym)).fetchall()
        stored.append({"symbol": sym, "rows": [list(map(str, r)) for r in rows]})
    integrity2 = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk2 = conn.execute("PRAGMA foreign_key_check").fetchall()
    snap_versions = conn.execute(
        """
        SELECT s.nse_symbol, COUNT(*) snaps, SUM(CASE WHEN fs.is_superseded THEN 1 ELSE 0 END) superseded
        FROM fundamental_snapshot fs JOIN stock_master s ON s.stock_id=fs.stock_id
        GROUP BY s.nse_symbol
        """
    ).fetchall()
    conn.close()

    report = {
        "backup": str(backup),
        "integrity_before": integrity,
        "fk_before": fk,
        "before": before,
        "preview": preview_rows,
        "sha_ok": sha_ok,
        "imported": imported,
        "failed": failed,
        "replay": replay,
        "after": after,
        "stored": stored,
        "snap_versions": [list(r) for r in snap_versions],
        "integrity_after": integrity2,
        "fk_after": fk2,
    }
    REPORT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("backup", "before", "after", "sha_ok", "failed", "snap_versions", "integrity_after", "fk_after")}, indent=2, default=str))
    print("imported", len(imported), "replay_dup", sum(1 for r in replay if r["body"].get("status") == "DUPLICATE"))


if __name__ == "__main__":
    main()
