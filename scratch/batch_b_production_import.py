"""STEP 3-6: controlled Batch B production import via OhlcvService.confirm_import.

Mirrors the Batch A workflow exactly: the application service performs every OHLCV
insert; no ad-hoc SQL writes. Aborts before, during, or after any failed gate.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
PROD = ROOT / "data" / "swing_trading.db"
NIFTY = ROOT / "manual_inputs" / "nse" / "Nifty50"
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.schemas.ohlcv import OhlcvConfirmRequest
from app.services.ohlcv_service import OhlcvService
from app.services.candidate_service import CandidateService
from app.services.candidate_config import ACTIVE_CANDIDATE_CONFIG

SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]
BATCH_A_SYMBOLS = ["ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
                   "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL"]
EXPECTED_ROWS = 247
OHLCV_BEFORE = 2469
OHLCV_AFTER = 4939

PRESERVE = {
    "fundamental_snapshot": 10, "candidate_evaluation_run": 33,
    "candidate_criterion_result": 297, "risk_reward_result": 29,
    "broker_recommendation": 5, "stock_master": 26,
}


def path_for(symbol: str) -> Path:
    return NIFTY / f"13-08-2025-TO-13-08-2026-{symbol}-ALL-N.csv"


def ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{PROD}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def phase5_fingerprint() -> dict:
    src = ROOT / "backend" / "app" / "services" / "candidate_config.py"
    conn = ro()
    run_fps = [dict(r) for r in conn.execute(
        "SELECT config_fingerprint, COUNT(*) n FROM candidate_evaluation_run "
        "GROUP BY config_fingerprint ORDER BY config_fingerprint")]
    conn.close()
    return {
        "candidate_config_py_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "active_config_name": ACTIVE_CANDIDATE_CONFIG.get("config_name"),
        "active_config_fingerprint": CandidateService.get_config_fingerprint(ACTIVE_CANDIDATE_CONFIG),
        "run_fingerprints": run_fps,
    }


def preserve_counts() -> dict:
    conn = ro()
    out = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in PRESERVE}
    conn.close()
    return out


def batch_a_snapshot() -> list:
    conn = ro()
    rows = [tuple(r) for r in conn.execute(
        "SELECT d.daily_ohlcv_id, d.stock_id, d.trading_date, d.series, d.open, d.high, "
        "d.low, d.close, d.volume, d.source_name, d.import_batch_id "
        "FROM daily_ohlcv d ORDER BY d.daily_ohlcv_id")]
    conn.close()
    return rows


def quality_report() -> dict:
    conn = ro()
    q = conn.execute
    out = {
        "ohlcv": q("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0],
        "synthetic": q("SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 "
                       "AND low=95 AND close=102 AND volume=1000").fetchone()[0],
        "duplicate_keys": q("SELECT COUNT(*) FROM (SELECT stock_id, trading_date, series, "
                            "COUNT(*) c FROM daily_ohlcv GROUP BY 1,2,3 HAVING c>1)").fetchone()[0],
        "invalid_ohlc": q("SELECT COUNT(*) FROM daily_ohlcv WHERE open<=0 OR high<=0 OR low<=0 "
                          "OR close<=0 OR NOT (low<=open AND open<=high AND low<=close "
                          "AND close<=high)").fetchone()[0],
        "negative_volume": q("SELECT COUNT(*) FROM daily_ohlcv WHERE volume<0").fetchone()[0],
        "non_eq_rows": q("SELECT COUNT(*) FROM daily_ohlcv WHERE series != 'EQ'").fetchone()[0],
        "missing_provenance": q("SELECT COUNT(*) FROM daily_ohlcv WHERE source_name IS NULL "
                                "OR source_name='' OR import_batch_id IS NULL").fetchone()[0],
        "orphan_batch": q("SELECT COUNT(*) FROM daily_ohlcv d LEFT JOIN data_import_batch b "
                          "ON b.import_batch_id=d.import_batch_id "
                          "WHERE b.import_batch_id IS NULL").fetchone()[0],
        "batches_without_sha": q("SELECT COUNT(*) FROM data_import_batch WHERE "
                                 "import_type='OHLCV_HISTORICAL' AND (file_sha256 IS NULL "
                                 "OR file_sha256='' OR original_filename IS NULL)").fetchone()[0],
        "integrity": q("PRAGMA integrity_check").fetchone()[0],
        "fk_violations": len(q("PRAGMA foreign_key_check").fetchall()),
    }
    conn.close()
    return out


def per_symbol(symbols: list[str]) -> dict:
    conn = ro()
    out = {}
    for sym in symbols:
        r = conn.execute(
            "SELECT s.stock_id, COUNT(*) rows, COUNT(DISTINCT d.trading_date) sessions, "
            "MIN(d.trading_date) lo, MAX(d.trading_date) hi, "
            "COUNT(DISTINCT d.series) series_kinds, "
            "SUM(CASE WHEN d.source_name IS NULL OR d.import_batch_id IS NULL THEN 1 ELSE 0 END) no_prov "
            "FROM stock_master s LEFT JOIN daily_ohlcv d ON d.stock_id=s.stock_id "
            "WHERE s.nse_symbol=? GROUP BY s.stock_id", (sym,)).fetchone()
        batches = [dict(b) for b in conn.execute(
            "SELECT DISTINCT b.import_batch_id, b.original_filename, b.file_sha256, b.source_name, "
            "b.source_reference FROM daily_ohlcv d JOIN data_import_batch b "
            "ON b.import_batch_id=d.import_batch_id JOIN stock_master s ON s.stock_id=d.stock_id "
            "WHERE s.nse_symbol=?", (sym,))]
        out[sym] = dict(r) | {"batches": batches}
    conn.close()
    return out


def run_import(label: str) -> dict:
    db = SessionLocal()
    totals = {"inserted": 0, "duplicates": 0, "conflicts": 0, "accepted": 0, "rejected": 0}
    detail = {}
    try:
        for sym in SYMBOLS:
            path = path_for(sym)
            content = path.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            req = OhlcvConfirmRequest(
                file_sha256=sha,
                original_filename=path.name,
                source_name="NSE",
                source_reference=f"manual_inputs/nse/Nifty50/{path.name}",
            )
            res = OhlcvService.confirm_import(db, req, content)
            detail[sym] = res
            totals["inserted"] += res["inserted"]
            totals["duplicates"] += res["rows_duplicates"]
            totals["conflicts"] += res["rows_conflicts"]
            totals["accepted"] += res["rows_accepted"]
            totals["rejected"] += res["rows_rejected"]
            print(f"  {label} {sym:<12} batch={res['import_batch_id']} inserted={res['inserted']} "
                  f"dup={res['rows_duplicates']} conf={res['rows_conflicts']} "
                  f"accepted={res['rows_accepted']} rejected={res['rows_rejected']}")
    finally:
        db.close()
    return {"totals": totals, "detail": detail}


def main() -> None:
    failures: list[str] = []

    def fail(msg: str) -> None:
        failures.append(msg)
        print("  FAILURE:", msg)

    print("=== BASELINE ===")
    preserve_before = preserve_counts()
    phase5_before = phase5_fingerprint()
    snapshot_before = batch_a_snapshot()
    quality_before = quality_report()
    batch_a_before = per_symbol(BATCH_A_SYMBOLS)
    conn = ro()
    batches_before = conn.execute("SELECT COUNT(*) FROM data_import_batch").fetchone()[0]
    conn.close()
    print("preserve:", json.dumps(preserve_before))
    print("phase5:", json.dumps(phase5_before))
    print("ohlcv:", quality_before["ohlcv"], "import_batches:", batches_before)

    if quality_before["ohlcv"] != OHLCV_BEFORE:
        fail(f"pre-import OHLCV {quality_before['ohlcv']} != {OHLCV_BEFORE}")
        raise SystemExit(1)

    print("\n=== STEP 3 - PRODUCTION IMPORT ===")
    first = run_import("IMPORT")
    print("TOTALS", json.dumps(first["totals"]))

    print("\n=== STEP 4 - POST-IMPORT VERIFICATION ===")
    quality_after = quality_report()
    print("quality:", json.dumps(quality_after))
    if first["totals"]["inserted"] != 2470:
        fail(f"inserted {first['totals']['inserted']} != 2470")
    if quality_after["ohlcv"] != OHLCV_AFTER:
        fail(f"OHLCV {quality_after['ohlcv']} != {OHLCV_AFTER}")
    for key in ("synthetic", "duplicate_keys", "invalid_ohlc", "negative_volume",
                "non_eq_rows", "missing_provenance", "orphan_batch", "batches_without_sha",
                "fk_violations"):
        if quality_after[key]:
            fail(f"{key} = {quality_after[key]}")
    if quality_after["integrity"] != "ok":
        fail(f"integrity_check = {quality_after['integrity']}")

    detail_after = per_symbol(SYMBOLS)
    print("\nPER-SYMBOL:")
    for sym, d in detail_after.items():
        prov_ok = d["no_prov"] == 0 and len(d["batches"]) >= 1
        print(f"  {sym:<12} stock_id={d['stock_id']:<3} rows={d['rows']} sessions={d['sessions']} "
              f"{str(d['lo'])[:10]}..{str(d['hi'])[:10]} series_kinds={d['series_kinds']} "
              f"provenance={'OK' if prov_ok else 'MISSING'}")
        if d["rows"] != EXPECTED_ROWS:
            fail(f"{sym} rows {d['rows']} != {EXPECTED_ROWS}")
        if d["sessions"] != EXPECTED_ROWS:
            fail(f"{sym} sessions {d['sessions']} != {EXPECTED_ROWS}")
        if str(d["lo"])[:10] != "2025-08-13":
            fail(f"{sym} earliest {d['lo']} != 2025-08-13")
        if str(d["hi"])[:10] != "2026-08-13":
            fail(f"{sym} latest {d['hi']} != 2026-08-13")
        if d["series_kinds"] != 1:
            fail(f"{sym} has {d['series_kinds']} series kinds")
        if not prov_ok:
            fail(f"{sym} provenance missing")

    batch_a_after = per_symbol(BATCH_A_SYMBOLS)
    if batch_a_before != batch_a_after:
        fail("Batch A per-symbol state changed")
    preserved_rows = [r for r in batch_a_snapshot() if r[0] <= max(x[0] for x in snapshot_before)]
    if preserved_rows != snapshot_before:
        fail("pre-existing OHLCV rows were modified")
    print("Batch A row-level snapshot preserved:", preserved_rows == snapshot_before)

    if failures:
        print("\nABORTING BEFORE REPLAY:", failures)
        raise SystemExit(2)

    print("\n=== STEP 5 - IDEMPOTENCY REPLAY ===")
    snapshot_post_import = batch_a_snapshot()
    conn = ro()
    batches_post_import = conn.execute("SELECT COUNT(*) FROM data_import_batch").fetchone()[0]
    conn.close()

    replay = run_import("REPLAY")
    print("TOTALS", json.dumps(replay["totals"]))

    quality_replay = quality_report()
    conn = ro()
    batches_post_replay = conn.execute("SELECT COUNT(*) FROM data_import_batch").fetchone()[0]
    conn.close()
    added = quality_replay["ohlcv"] - quality_after["ohlcv"]
    print(f"additional OHLCV rows on replay: {added}")
    print(f"import_batch rows: before={batches_before} after_import={batches_post_import} "
          f"after_replay={batches_post_replay}")
    if added != 0:
        fail(f"replay inserted {added} rows")
    if replay["totals"]["inserted"] != 0:
        fail(f"replay reported {replay['totals']['inserted']} inserts")
    if replay["totals"]["conflicts"]:
        fail(f"replay reported {replay['totals']['conflicts']} conflicts")
    if quality_replay["ohlcv"] != OHLCV_AFTER:
        fail(f"post-replay OHLCV {quality_replay['ohlcv']} != {OHLCV_AFTER}")
    if batch_a_snapshot() != snapshot_post_import:
        fail("replay mutated existing OHLCV rows")
    print("OHLCV rows byte-identical after replay:", batch_a_snapshot() == snapshot_post_import)

    print("\n=== STEP 6 - PRESERVATION ===")
    preserve_after = preserve_counts()
    phase5_after = phase5_fingerprint()
    for table, expected in PRESERVE.items():
        before, after = preserve_before[table], preserve_after[table]
        ok = before == after == expected
        print(f"  {table:<28} {before} -> {after} (expected {expected}) {'OK' if ok else 'DRIFT'}")
        if not ok:
            fail(f"{table} drifted: {before} -> {after}")
    print("  phase5 config unchanged:", phase5_before == phase5_after)
    if phase5_before != phase5_after:
        fail("Phase 5 configuration changed")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "manual_inputs" / "batch_b" / f"batch_b_import_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "generated_at": stamp,
        "import_totals": first["totals"], "import_detail": first["detail"],
        "replay_totals": replay["totals"], "replay_detail": replay["detail"],
        "per_symbol": detail_after,
        "quality_before": quality_before, "quality_after": quality_after,
        "quality_after_replay": quality_replay,
        "preserve_before": preserve_before, "preserve_after": preserve_after,
        "phase5_before": phase5_before, "phase5_after": phase5_after,
        "import_batches": {"before": batches_before, "after_import": batches_post_import,
                           "after_replay": batches_post_replay},
        "post_change_db_sha256": hashlib.sha256(PROD.read_bytes()).hexdigest(),
    }, indent=2, default=str), encoding="utf-8")
    print("\nREPORT", out)
    print("POST_IMPORT_DB_SHA256", hashlib.sha256(PROD.read_bytes()).hexdigest())

    if failures:
        print("\nIMPORT FAILED:", failures)
        raise SystemExit(3)
    print("\nBATCH_B_IMPORT_OK")


if __name__ == "__main__":
    main()
