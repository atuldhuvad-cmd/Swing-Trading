"""Back up production, apply the INSURANCE entity-type migration, verify data preserved."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
sys.path.insert(0, str(ROOT / "backend"))
from app.schema_readiness import guard_script_write  # noqa: E402  (refuses a stale schema before any write)
BACKEND = ROOT / "backend"
PY = BACKEND / "venv" / "Scripts" / "python.exe"

TABLES = ["fundamental_snapshot", "fundamental_metric", "daily_ohlcv", "stock_master",
          "candidate_evaluation_run", "candidate_criterion_result", "risk_reward_result",
          "broker_recommendation", "source_reference", "data_import_batch"]


def snapshot() -> dict:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    state = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    state["snapshot_rows"] = [tuple(r) for r in conn.execute(
        "SELECT snapshot_id, stock_id, as_of_date, financial_period, period_type, "
        "source_reference_id, version, is_superseded, superseded_by_id, entity_type, "
        "statement_scope, source_line_item, original_unit FROM fundamental_snapshot "
        "ORDER BY snapshot_id")]
    state["metric_rows"] = [tuple(r) for r in conn.execute(
        "SELECT metric_id, snapshot_id, metric_name, metric_value, status "
        "FROM fundamental_metric ORDER BY metric_id")]
    state["ddl"] = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='fundamental_snapshot'").fetchone()[0]
    state["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    state["fk_violations"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    state["alembic"] = conn.execute("SELECT * FROM alembic_version").fetchall()
    conn.close()
    return state


def main() -> None:
    guard_script_write(DB)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB.parent / "safety_backups" / f"swing_trading_PRE_INSURANCE_MIGRATION_{stamp}.db"
    backup.parent.mkdir(parents=True, exist_ok=True)
    pre_sha = hashlib.sha256(DB.read_bytes()).hexdigest()
    shutil.copy2(DB, backup)
    print("BACKUP_PATH  ", backup)
    print("BACKUP_SHA256", hashlib.sha256(backup.read_bytes()).hexdigest())
    print("PRE_SHA256   ", pre_sha)

    before = snapshot()
    print("\nBEFORE alembic:", before["alembic"])
    print("BEFORE DDL check:", "INSURANCE" in before["ddl"])
    print("BEFORE counts:", json.dumps({k: before[k] for k in TABLES}))

    proc = subprocess.run([str(PY), "-m", "alembic", "upgrade", "head"],
                          cwd=str(BACKEND), capture_output=True, text=True)
    print("\n--- alembic stdout ---\n" + proc.stdout)
    print("--- alembic stderr ---\n" + proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(f"alembic failed with code {proc.returncode}")

    after = snapshot()
    print("AFTER alembic:", after["alembic"])
    print("AFTER DDL:", after["ddl"].strip().splitlines()[-2].strip())
    print("AFTER counts:", json.dumps({k: after[k] for k in TABLES}))

    failures = []
    if "INSURANCE" not in after["ddl"]:
        failures.append("CHECK constraint does not include INSURANCE")
    for t in TABLES:
        if before[t] != after[t]:
            failures.append(f"{t} count changed {before[t]} -> {after[t]}")
    if before["snapshot_rows"] != after["snapshot_rows"]:
        failures.append("fundamental_snapshot rows changed")
    if before["metric_rows"] != after["metric_rows"]:
        failures.append("fundamental_metric rows changed")
    if after["integrity"] != "ok":
        failures.append(f"integrity_check = {after['integrity']}")
    if after["fk_violations"]:
        failures.append(f"{after['fk_violations']} FK violations")

    print("\nsnapshot rows identical:", before["snapshot_rows"] == after["snapshot_rows"])
    print("metric rows identical  :", before["metric_rows"] == after["metric_rows"])
    print("integrity_check        :", after["integrity"])
    print("foreign_key_check      :", after["fk_violations"])
    print("POST_SHA256            :", hashlib.sha256(DB.read_bytes()).hexdigest())

    # Prove the widened constraint accepts INSURANCE and still rejects junk, without
    # leaving any row behind.
    conn = sqlite3.connect(DB)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO fundamental_snapshot (stock_id, as_of_date, captured_at, version, "
            "is_superseded, entity_type) VALUES ((SELECT stock_id FROM stock_master LIMIT 1), "
            "'2026-03-31', '2026-03-31 00:00:00', 1, 0, 'INSURANCE')")
        print("constraint accepts INSURANCE: True")
        try:
            conn.execute(
                "INSERT INTO fundamental_snapshot (stock_id, as_of_date, captured_at, version, "
                "is_superseded, entity_type) VALUES ((SELECT stock_id FROM stock_master LIMIT 1), "
                "'2026-03-31', '2026-03-31 00:00:00', 1, 0, 'NOT_A_TYPE')")
            failures.append("constraint accepted an invalid entity_type")
            print("constraint rejects invalid : False")
        except sqlite3.IntegrityError:
            print("constraint rejects invalid : True")
    finally:
        conn.rollback()
        conn.close()

    final = snapshot()
    if final["snapshot_rows"] != before["snapshot_rows"]:
        failures.append("probe left rows behind")
    print("no probe rows persisted:", final["snapshot_rows"] == before["snapshot_rows"])
    print("final snapshot count   :", final["fundamental_snapshot"])

    if failures:
        print("\nMIGRATION FAILED:", failures)
        raise SystemExit(1)
    print("\nMIGRATION_OK")


if __name__ == "__main__":
    main()
