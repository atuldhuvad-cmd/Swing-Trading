"""Controlled Batch B fundamental production import via POST /api/fundamentals/confirm.

Abort unless preview recheck matches the approved non-persistent preview.
Does not run Phase 5 candidate re-evaluation.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
INTAKE = ROOT / "manual_inputs" / "fundamentals" / "batch_b_manual_intake.json"
APPROVED = ROOT / "manual_inputs" / "fundamentals" / "batch_b_preview_results.json"
REPORT = ROOT / "manual_inputs" / "fundamentals" / "batch_b_import_report.json"

sys.path.insert(0, str(ROOT / "backend"))
from app.main import app  # noqa: E402

BATCH_B = [
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
]
BATCH_A = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
]
EXPECTED_REV = {
    "CIPLA": Decimal("28162.59"),
    "COALINDIA": Decimal("168400.29"),
    "DRREDDY": Decimal("33700.2"),
    "EICHERMOT": Decimal("23407.56"),
    "ETERNAL": Decimal("54364"),
    "GRASIM": Decimal("175430.74"),
    "HCLTECH": Decimal("130144"),
    "HDFCBANK": Decimal("495462.81"),
    "HDFCLIFE": Decimal("98770.38"),
    "HINDALCO": Decimal("274944"),
}
EXPECTED_ENTITY = {
    "CIPLA": "ORDINARY",
    "COALINDIA": "ORDINARY",
    "DRREDDY": "ORDINARY",
    "EICHERMOT": "ORDINARY",
    "ETERNAL": "ORDINARY",
    "GRASIM": "ORDINARY",
    "HCLTECH": "ORDINARY",
    "HDFCBANK": "BANK",
    "HDFCLIFE": "INSURANCE",
    "HINDALCO": "ORDINARY",
}
EXPECTED_LINE = {
    "ORDINARY": "Revenue from Operations",
    "BANK": "Total Income",
    "INSURANCE": "Total Income (Policyholders' Account)",
}

TABLES = [
    "fundamental_snapshot",
    "fundamental_metric",
    "data_import_batch",
    "daily_ohlcv",
    "candidate_evaluation_run",
    "candidate_criterion_result",
    "risk_reward_result",
    "broker_recommendation",
    "source_reference",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counts(conn: sqlite3.Connection) -> dict:
    out = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    out["fundamental_manual_batches"] = conn.execute(
        "SELECT COUNT(*) FROM data_import_batch WHERE import_type='FUNDAMENTAL_MANUAL'"
    ).fetchone()[0]
    out["synthetic_ohlcv"] = conn.execute(
        "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
    ).fetchone()[0]
    out["batch_b_snapshots"] = conn.execute(
        """
        SELECT COUNT(*) FROM fundamental_snapshot fs
        JOIN stock_master s ON s.stock_id=fs.stock_id
        WHERE s.nse_symbol IN ({})
        """.format(",".join("?" * len(BATCH_B))),
        BATCH_B,
    ).fetchone()[0]
    out["batch_a_snapshots"] = conn.execute(
        """
        SELECT COUNT(*) FROM fundamental_snapshot fs
        JOIN stock_master s ON s.stock_id=fs.stock_id
        WHERE s.nse_symbol IN ({})
        """.format(",".join("?" * len(BATCH_A))),
        BATCH_A,
    ).fetchone()[0]
    return out


def snapshot_fingerprint(conn: sqlite3.Connection, symbols: list[str]) -> list[dict]:
    q = """
    SELECT s.nse_symbol, fs.snapshot_id, fs.version, fs.is_superseded, fs.entity_type,
           fs.financial_period, fs.period_type, fs.as_of_date, fs.statement_scope,
           fs.source_line_item, fs.original_unit, fs.captured_at, fs.source_reference_id,
           fm.metric_value, fm.status
    FROM fundamental_snapshot fs
    JOIN stock_master s ON s.stock_id=fs.stock_id
    JOIN fundamental_metric fm ON fm.snapshot_id=fs.snapshot_id AND fm.metric_name='revenue'
    WHERE s.nse_symbol IN ({})
    ORDER BY s.nse_symbol, fs.snapshot_id
    """.format(",".join("?" * len(symbols)))
    cols = [
        "nse_symbol", "snapshot_id", "version", "is_superseded", "entity_type",
        "financial_period", "period_type", "as_of_date", "statement_scope",
        "source_line_item", "original_unit", "captured_at", "source_reference_id",
        "metric_value", "status",
    ]
    return [dict(zip(cols, row)) for row in conn.execute(q, symbols).fetchall()]


def abort(report: dict, reason: str) -> None:
    report["stop"] = reason
    REPORT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    raise SystemExit(reason)


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "data" / "safety_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"swing_trading_PRE_FUND_BATCH_B_{stamp}.db"

    pre_sha = sha256_file(DB)
    shutil.copy2(DB, backup)
    backup_sha = sha256_file(backup)
    if backup_sha != pre_sha:
        abort({"backup": str(backup), "pre_sha": pre_sha, "backup_sha": backup_sha}, "backup SHA mismatch")

    bconn = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    integrity = bconn.execute("PRAGMA integrity_check").fetchone()[0]
    fk = bconn.execute("PRAGMA foreign_key_check").fetchall()
    bconn.close()
    if integrity != "ok" or fk:
        abort({"backup": str(backup), "integrity": integrity, "fk": fk}, "backup integrity/FK failed")

    conn = sqlite3.connect(str(DB))
    before = counts(conn)
    batch_a_before = snapshot_fingerprint(conn, BATCH_A)
    conn.close()

    approved_rows = json.loads(APPROVED.read_text(encoding="utf-8"))["results"]
    approved = {r["symbol"]: r for r in approved_rows}
    intake = json.loads(INTAKE.read_text(encoding="utf-8"))

    client = TestClient(app)
    preview_rows = []
    for stock in intake["stocks"]:
        payload = stock["payload"]
        res = client.post("/api/fundamentals/preview", json=payload)
        body = res.json()
        exp = approved[stock["nse_symbol"]]
        row = {
            "symbol": stock["nse_symbol"],
            "http": res.status_code,
            "action": body.get("action"),
            "persisted": body.get("persisted"),
            "sha": body.get("payload_sha256"),
            "approved_sha": exp["payload_sha256"],
            "sha_match": body.get("payload_sha256") == exp["payload_sha256"],
            "line": body.get("source_line_item"),
            "scope": body.get("statement_scope"),
            "unit": body.get("original_unit"),
            "period": body.get("financial_period"),
            "as_of_date": body.get("as_of_date"),
            "errors": body.get("errors") or body.get("detail"),
        }
        preview_rows.append(row)

    report = {
        "backup": str(backup),
        "backup_sha256": backup_sha,
        "production_pre_import_sha256": pre_sha,
        "sha_identical": backup_sha == pre_sha,
        "integrity_before": integrity,
        "fk_before": fk,
        "before": before,
        "preview_recheck": preview_rows,
    }
    bad = [
        r for r in preview_rows
        if r["http"] != 200
        or r["action"] != "ACCEPTED"
        or r["persisted"] is not False
        or not r["sha_match"]
        or r["period"] != "FY2025-26"
        or r["as_of_date"] != "2026-03-31"
        or r["scope"] != "CONSOLIDATED"
    ]
    if bad:
        abort(report, f"preview recheck failed: {bad}")

    imported = []
    failed = []
    for stock in intake["stocks"]:
        payload = stock["payload"]
        sha = approved[stock["nse_symbol"]]["payload_sha256"]
        res = client.post(
            "/api/fundamentals/confirm",
            json={"payload_sha256": sha, "payload": payload},
        )
        body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {"raw": res.text}
        row = {"symbol": stock["nse_symbol"], "http": res.status_code, "body": body}
        if res.status_code != 200 or not body.get("persisted"):
            failed.append(row)
            abort({**report, "imported": imported, "failed": failed}, f"import failed for {stock['nse_symbol']}")
        imported.append(row)

    replay = []
    for stock in intake["stocks"]:
        payload = stock["payload"]
        sha = approved[stock["nse_symbol"]]["payload_sha256"]
        res = client.post(
            "/api/fundamentals/confirm",
            json={"payload_sha256": sha, "payload": payload},
        )
        replay.append({"symbol": stock["nse_symbol"], "http": res.status_code, "body": res.json()})

    conn = sqlite3.connect(str(DB))
    after = counts(conn)
    batch_a_after = snapshot_fingerprint(conn, BATCH_A)
    stored = snapshot_fingerprint(conn, BATCH_B)
    hdfclife = [r for r in stored if r["nse_symbol"] == "HDFCLIFE"]
    integrity2 = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk2 = conn.execute("PRAGMA foreign_key_check").fetchall()
    current_counts = conn.execute(
        """
        SELECT s.nse_symbol, COUNT(*) snaps,
               SUM(CASE WHEN fs.is_superseded THEN 1 ELSE 0 END) superseded,
               SUM(CASE WHEN NOT fs.is_superseded THEN 1 ELSE 0 END) current
        FROM fundamental_snapshot fs JOIN stock_master s ON s.stock_id=fs.stock_id
        WHERE s.nse_symbol IN ({})
        GROUP BY s.nse_symbol
        """.format(",".join("?" * len(BATCH_B))),
        BATCH_B,
    ).fetchall()
    conn.close()

    defects = []
    if after["daily_ohlcv"] != before["daily_ohlcv"]:
        defects.append("OHLCV changed")
    if after["synthetic_ohlcv"] != 0:
        defects.append("synthetic OHLCV present")
    if after["candidate_evaluation_run"] != before["candidate_evaluation_run"]:
        defects.append("candidate runs changed")
    if after["candidate_criterion_result"] != before["candidate_criterion_result"]:
        defects.append("criterion rows changed")
    if after["risk_reward_result"] != before["risk_reward_result"]:
        defects.append("RR rows changed")
    if after["broker_recommendation"] != before["broker_recommendation"]:
        defects.append("broker recommendations changed")
    if batch_a_before != batch_a_after:
        defects.append("Batch A snapshots mutated")
    if after["batch_a_snapshots"] != 10:
        defects.append("Batch A snapshot count changed")
    if after["fundamental_snapshot"] != before["fundamental_snapshot"] + 10:
        defects.append(f"snapshot count {before['fundamental_snapshot']} -> {after['fundamental_snapshot']}")
    if after["batch_b_snapshots"] != 10:
        defects.append(f"Batch B snapshots {after['batch_b_snapshots']}")

    for row in stored:
        sym = row["nse_symbol"]
        entity = EXPECTED_ENTITY[sym]
        if int(row["is_superseded"]):
            defects.append(f"{sym} superseded unexpectedly")
        if int(row["version"]) != 1:
            defects.append(f"{sym} version {row['version']}")
        if row["entity_type"] != entity:
            defects.append(f"{sym} entity {row['entity_type']}")
        if row["financial_period"] != "FY2025-26" or row["period_type"] != "ANNUAL":
            defects.append(f"{sym} period mismatch")
        if str(row["as_of_date"])[:10] != "2026-03-31":
            defects.append(f"{sym} as_of_date {row['as_of_date']}")
        if row["statement_scope"] != "CONSOLIDATED":
            defects.append(f"{sym} scope {row['statement_scope']}")
        if row["source_line_item"] != EXPECTED_LINE[entity]:
            defects.append(f"{sym} line {row['source_line_item']}")
        if Decimal(str(row["metric_value"])) != EXPECTED_REV[sym]:
            defects.append(f"{sym} revenue {row['metric_value']}")
        if row["status"] != "KNOWN":
            defects.append(f"{sym} status {row['status']}")

    if len(hdfclife) != 1:
        defects.append(f"HDFCLIFE snapshot count {len(hdfclife)}")
    else:
        h = hdfclife[0]
        if h["entity_type"] != "INSURANCE":
            defects.append("HDFCLIFE entity not INSURANCE")
        if h["source_line_item"] != "Total Income (Policyholders' Account)":
            defects.append("HDFCLIFE source line incorrect")
        if h["source_line_item"] and "Shareholders" in h["source_line_item"]:
            defects.append("HDFCLIFE shareholders line persisted")

    replay_ok = all(
        r["http"] == 200
        and r["body"].get("status") == "DUPLICATE"
        and r["body"].get("persisted") is False
        and r["body"].get("audit_status") == "SKIPPED_IDEMPOTENT"
        for r in replay
    )
    if not replay_ok:
        defects.append("idempotent replay failed")
    if after["batch_b_snapshots"] != 10:
        defects.append("duplicate snapshots created")

    report.update(
        {
            "imported": imported,
            "failed": failed,
            "replay": replay,
            "after": after,
            "stored": stored,
            "current_counts": [list(r) for r in current_counts],
            "batch_a_unchanged": batch_a_before == batch_a_after,
            "hdfclife": hdfclife,
            "integrity_after": integrity2,
            "fk_after": fk2,
            "defects": defects,
        }
    )
    REPORT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(
        {
            "backup": str(backup),
            "backup_sha256": backup_sha,
            "production_pre_import_sha256": pre_sha,
            "before": before,
            "after": after,
            "imported": len(imported),
            "failed": failed,
            "replay_dup": sum(1 for r in replay if r["body"].get("status") == "DUPLICATE"),
            "batch_a_unchanged": batch_a_before == batch_a_after,
            "hdfclife": hdfclife,
            "integrity_after": integrity2,
            "fk_after": fk2,
            "defects": defects,
        },
        indent=2,
        default=str,
    ))
    if defects:
        raise SystemExit("IMPORT VERIFICATION FAILED")


if __name__ == "__main__":
    main()
