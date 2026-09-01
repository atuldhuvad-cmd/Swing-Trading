"""Batch B NON-PERSISTENT preview through the production OhlcvService.

The ORM session is rolled back and never committed. Parser behaviour is untouched.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
SRC = ROOT / "manual_inputs" / "nse" / "Nifty50"
OUT_DIR = ROOT / "manual_inputs" / "batch_b"
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.models import StockMaster
from app.services.ohlcv_service import OhlcvService

MIN_SESSIONS = 200
EXPECTED_SHA = {
    "CIPLA": "a0352bff049b6bc452944c2b0ac78928aab8c5a66937d793d824b4f8a5593b5c",
    "COALINDIA": "85b8a1150d1740074e5464f680c642d46a8d19478864874cd906e8feb9d3e4dc",
    "DRREDDY": "8608cb8ab0671951f144b8eb99ce0de0be565c0b8dc1bb895c07edba59194720",
    "EICHERMOT": "d7da7cccd5191f43544c75a434bee700d961aa6de27cf57c1d69b9fec49238a8",
    "ETERNAL": "fc3aed490c2a127f82ba14b3168fc5292be1d692fc6f830e6572eb7245cabc8f",
    "GRASIM": "c457abb57f4a855a782778948a21063e30dea0a42c7d344fd38631ecd3838269",
    "HCLTECH": "d01222ab542dc511f5dcbe65530b68ffaa599b72397c2f4cb8d49e2ea96b3e95",
    "HDFCBANK": "b226a83c697306e81e16b3374d47bb2ab311ad998558bd0990fb5a5f96c43efd",
    "HDFCLIFE": "0f5f11d3a546551cb37dae1d49749e62563d45f1a997049909582940f7a29e9a",
    "HINDALCO": "310d81bc101f7d1c7aa249f9cc7a179a72769c899a01cbde0ccc234f7600e60d",
}
COUNT_TABLES = {
    "daily_ohlcv": 2469, "candidate_evaluation_run": 33, "candidate_criterion_result": 297,
    "risk_reward_result": 29, "fundamental_snapshot": 10, "broker_recommendation": 5,
    "stock_master": None, "data_import_batch": None,
}


def production_state() -> dict:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        s = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in COUNT_TABLES}
        s["synthetic_ohlcv"] = conn.execute(
            "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
        ).fetchone()[0]
        s["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        s["fk_violations"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()
    return s


def main() -> None:
    before = production_state()
    print("PRODUCTION_BEFORE", json.dumps(before))

    db = SessionLocal()
    results = []
    totals = {k: 0 for k in ("physical", "eq", "ignored", "accepted", "rejected",
                             "duplicates", "conflicts", "unmapped")}
    try:
        registered = {s.nse_symbol: s.stock_id for s in db.query(StockMaster).all()}
        print("\n=== STOCK MASTER REGISTRATION ===")
        for sym in EXPECTED_SHA:
            print(f"  {sym:<12} {'registered id=' + str(registered[sym]) if sym in registered else 'NOT REGISTERED'}")

        for sym, want_sha in EXPECTED_SHA.items():
            path = SRC / f"13-08-2025-TO-13-08-2026-{sym}-ALL-N.csv"
            entry: dict = {"symbol": sym, "expected_sha256": want_sha,
                           "registered_in_master": sym in registered}
            if not path.exists():
                entry.update({"status": "FILE_MISSING", "filename": path.name})
                results.append(entry)
                continue

            content = path.read_bytes()
            actual_sha = hashlib.sha256(content).hexdigest()
            sha_ok = actual_sha == want_sha

            preview = OhlcvService.parse_historical_file(db, content, path.name)

            eq_rows = [r for r in preview.preview_rows if (r.series or "").upper() == "EQ"]
            dates = sorted({r.trading_date for r in eq_rows if r.trading_date})
            statuses: dict[str, int] = {}
            for r in preview.preview_rows:
                statuses[r.status] = statuses.get(r.status, 0) + 1

            sessions = len(dates)
            entry.update({
                "filename": path.name,
                "actual_sha256": actual_sha,
                "sha_match": sha_ok,
                "service_sha256": preview.file_sha256,
                "service_sha_match": preview.file_sha256 == want_sha,
                "physical_rows": preview.rows_received,
                "eq_rows": preview.rows_received - preview.rows_ignored,
                "non_eq_filtered": preview.rows_ignored,
                "accepted": preview.rows_accepted,
                "invalid_eq": preview.rows_rejected,
                "duplicates": preview.rows_duplicates,
                "conflicts": preview.rows_conflicts,
                "unmapped": preview.rows_unmapped,
                "preview_row_statuses": statuses,
                "earliest": dates[0] if dates else None,
                "latest": dates[-1] if dates else None,
                "unique_sessions": sessions,
                "ge_200": sessions >= MIN_SESSIONS,
                "sma200_ready": sessions >= MIN_SESSIONS,
            })
            problems = []
            if not sha_ok:
                problems.append("SHA-256 mismatch")
            if preview.rows_rejected:
                problems.append(f"{preview.rows_rejected} invalid EQ row(s)")
            if preview.rows_conflicts:
                problems.append(f"{preview.rows_conflicts} conflict(s)")
            if preview.rows_duplicates:
                problems.append(f"{preview.rows_duplicates} duplicate(s)")
            if sessions < MIN_SESSIONS:
                problems.append(f"only {sessions} sessions")
            if preview.rows_unmapped:
                problems.append(f"{preview.rows_unmapped} unmapped (symbol absent from stock_master)")
            entry["status"] = "PREVIEW_OK" if not problems else "BLOCKED: " + "; ".join(problems)
            results.append(entry)

            totals["physical"] += preview.rows_received
            totals["eq"] += preview.rows_received - preview.rows_ignored
            totals["ignored"] += preview.rows_ignored
            totals["accepted"] += preview.rows_accepted
            totals["rejected"] += preview.rows_rejected
            totals["duplicates"] += preview.rows_duplicates
            totals["conflicts"] += preview.rows_conflicts
            totals["unmapped"] += preview.rows_unmapped
    finally:
        db.rollback()
        db.close()

    after = production_state()

    print("\n=== PER-SYMBOL APPLICATION PREVIEW ===")
    for r in results:
        print(f"\n{r['symbol']}")
        if r["status"] == "FILE_MISSING":
            print("  FILE MISSING")
            continue
        print(f"  File            : {r['filename']}")
        print(f"  SHA match       : {r['sha_match']} (service reported: {r['service_sha_match']})")
        print(f"  Registered      : {r['registered_in_master']}")
        print(f"  Physical rows   : {r['physical_rows']}")
        print(f"  EQ rows         : {r['eq_rows']}")
        print(f"  Non-EQ filtered : {r['non_eq_filtered']}")
        print(f"  Accepted        : {r['accepted']}")
        print(f"  Invalid EQ      : {r['invalid_eq']}")
        print(f"  Duplicates      : {r['duplicates']}")
        print(f"  Conflicts       : {r['conflicts']}")
        print(f"  Unmapped        : {r['unmapped']}")
        print(f"  Row statuses    : {r['preview_row_statuses']}")
        print(f"  Date range      : {r['earliest']} to {r['latest']}")
        print(f"  Unique sessions : {r['unique_sessions']}")
        print(f"  SMA200-ready    : {r['sma200_ready']}")
        print(f"  Status          : {r['status']}")

    print("\n=== TOTALS ===")
    print(json.dumps(totals, indent=2))
    ok = sum(1 for r in results if r["status"] == "PREVIEW_OK")
    ge200 = sum(1 for r in results if r.get("ge_200"))
    print(f"PREVIEW_OK {ok}/{len(EXPECTED_SHA)}   >=200 sessions {ge200}/{len(EXPECTED_SHA)}")
    print("SHA mismatches:", [r["symbol"] for r in results if r.get("sha_match") is False])
    print("Unregistered symbols:", [r["symbol"] for r in results if not r["registered_in_master"]])

    print("\nPRODUCTION_AFTER ", json.dumps(after))
    drift = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    print("PRODUCTION_DRIFT", json.dumps(drift))
    if drift:
        raise SystemExit("STOP_PRODUCTION_WRITE_DETECTED")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"batch_b_app_preview_{stamp}.json"
    out.write_text(json.dumps({"generated_at": stamp, "results": results, "totals": totals,
                               "production_before": before, "production_after": after},
                              indent=2), encoding="utf-8")
    print("REPORT", out)


if __name__ == "__main__":
    main()
