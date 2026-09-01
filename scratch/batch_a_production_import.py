"""Controlled Batch A production import via OhlcvService.confirm_import (not ad-hoc SQL)."""
from __future__ import annotations

import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text
from app.database import SessionLocal
from app.schemas.ohlcv import OhlcvConfirmRequest
from app.services.ohlcv_service import OhlcvService

PROD = ROOT / "data" / "swing_trading.db"
NIFTY = ROOT / "manual_inputs" / "nse" / "Nifty50"
SYMBOLS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
]
EXPECTED = {
    "ADANIENT": 247, "ADANIPORTS": 247, "APOLLOHOSP": 247, "ASIANPAINT": 247,
    "AXISBANK": 247, "BAJAJ-AUTO": 247, "BAJAJFINSV": 247, "BAJFINANCE": 247,
    "BEL": 247, "BHARTIARTL": 246,
}


def pick_file(symbol: str) -> Path:
    matches = [
        p for p in NIFTY.glob("*.csv")
        if f"-{symbol}-ALL-N" in p.name and "Quote-SLB" not in p.name
    ]
    if not matches:
        raise FileNotFoundError(symbol)
    return sorted(matches, key=lambda p: p.name)[-1]


def counts(conn: sqlite3.Connection) -> dict:
    tables = [
        "daily_ohlcv", "data_import_batch", "broker_recommendation",
        "source_reference", "recommendation_source",
    ]
    out = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    out["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    out["fk"] = conn.execute("PRAGMA foreign_key_check").fetchall()
    return out


def snapshot_ohlcv(conn: sqlite3.Connection):
    return list(conn.execute(
        """SELECT stock_id, trading_date, series, open, high, low, close, volume,
                  source_name, import_batch_id
           FROM daily_ohlcv ORDER BY stock_id, trading_date, series"""
    ))


def preview_all(db) -> dict:
    totals = defaultdict(int)
    files = []
    for symbol in SYMBOLS:
        path = pick_file(symbol)
        content = path.read_bytes()
        preview = OhlcvService.parse_historical_file(db, content, path.name)
        files.append((path, content, preview))
        totals["files"] += 1
        totals["physical"] += preview.rows_received
        totals["eq"] += (
            preview.rows_accepted + preview.rows_rejected + preview.rows_unmapped
            + preview.rows_duplicates + preview.rows_conflicts
        )
        totals["ignored"] += preview.rows_ignored
        totals["accepted"] += preview.rows_accepted
        totals["invalid"] += preview.rows_rejected
        totals["unmapped"] += preview.rows_unmapped
        totals["duplicates"] += preview.rows_duplicates
        totals["conflicts"] += preview.rows_conflicts
        by = defaultdict(int)
        for row in preview.preview_rows:
            if row.status == "ACCEPTED":
                by[row.symbol] += 1
        print("PREVIEW", path.name, dict(by), "accepted", preview.rows_accepted,
              "ignored", preview.rows_ignored, "sha", preview.file_sha256)
    print("FILES", totals["files"])
    print("PHYSICAL", totals["physical"])
    print("EQ", totals["eq"])
    print("NON_EQ", totals["ignored"])
    print("ACCEPTED", totals["accepted"])
    print("INVALID_EQ", totals["invalid"])
    print("UNMAPPED", totals["unmapped"])
    print("DUPLICATES", totals["duplicates"])
    print("CONFLICTS", totals["conflicts"])
    return {"totals": totals, "files": files}


def verify_quality(conn: sqlite3.Connection) -> dict:
    dups = conn.execute(
        """SELECT COUNT(*) FROM (
             SELECT stock_id, trading_date, series, COUNT(*) c
             FROM daily_ohlcv GROUP BY 1,2,3 HAVING c>1)"""
    ).fetchone()[0]
    invalid = conn.execute(
        """SELECT COUNT(*) FROM daily_ohlcv
           WHERE open<=0 OR high<=0 OR low<=0 OR close<=0
              OR NOT (low<=open AND open<=high AND low<=close AND close<=high)"""
    ).fetchone()[0]
    neg_vol = conn.execute("SELECT COUNT(*) FROM daily_ohlcv WHERE volume<0").fetchone()[0]
    missing_prov = conn.execute(
        """SELECT COUNT(*) FROM daily_ohlcv
           WHERE source_name IS NULL OR source_name=''
              OR import_batch_id IS NULL"""
    ).fetchone()[0]
    missing_sha = conn.execute(
        """SELECT COUNT(*) FROM data_import_batch b
           WHERE b.import_type='OHLCV_HISTORICAL'
             AND (b.file_sha256 IS NULL OR b.file_sha256=''
                  OR b.original_filename IS NULL)"""
    ).fetchone()[0]
    per = list(conn.execute(
        """SELECT s.nse_symbol, COUNT(*)
           FROM daily_ohlcv d JOIN stock_master s ON s.stock_id=d.stock_id
           GROUP BY s.nse_symbol ORDER BY s.nse_symbol"""
    ))
    return {
        "dups": dups, "invalid": invalid, "neg_vol": neg_vol,
        "missing_prov": missing_prov, "missing_sha": missing_sha, "per": per,
        "n": conn.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0],
        "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
        "fk": conn.execute("PRAGMA foreign_key_check").fetchall(),
    }


def main():
    if not PROD.exists():
        raise SystemExit("PRODUCTION DB MISSING")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "data" / f"swing_trading_backup_{stamp}.db"
    shutil.copy2(PROD, backup)
    print("BACKUP", backup)

    conn = sqlite3.connect(PROD)
    conn.execute("PRAGMA foreign_keys=ON")
    before = counts(conn)
    print("BEFORE", before)
    conn.close()

    db = SessionLocal()
    try:
        gate = preview_all(db)
        t = gate["totals"]
        ohlcv_now = db.execute(text("SELECT COUNT(*) FROM daily_ohlcv")).scalar()
        print("PREVIEW_DID_NOT_PERSIST", ohlcv_now)
        if (
            t["files"] != 10 or t["accepted"] != 2469 or t["invalid"] != 0
            or t["unmapped"] != 0 or t["duplicates"] != 0 or t["conflicts"] != 0
        ):
            print("STOP_PREVIEW_GATE_FAILED", dict(t))
            raise SystemExit(2)

        inserted_total = 0
        for path, content, preview in gate["files"]:
            req = OhlcvConfirmRequest(
                file_sha256=preview.file_sha256,
                original_filename=path.name,
                source_name="NSE",
                source_reference=f"manual_inputs/nse/Nifty50/{path.name}",
            )
            res = OhlcvService.confirm_import(db, req, content)
            inserted_total += res["inserted"]
            print("IMPORT", path.name, res)
        print("IMPORTED_INSERTED", inserted_total)
    finally:
        db.close()

    conn = sqlite3.connect(PROD)
    conn.execute("PRAGMA foreign_keys=ON")
    after = verify_quality(conn)
    print("AFTER_IMPORT", after)
    snap1 = snapshot_ohlcv(conn)
    rec_after = conn.execute("SELECT COUNT(*) FROM broker_recommendation").fetchone()[0]
    print("REC_AFTER_IMPORT", rec_after)
    conn.close()

    if after["n"] != 2469 or after["dups"] or after["invalid"] or after["neg_vol"] or after["missing_prov"]:
        print("STOP_POST_IMPORT_QUALITY_FAILED")
        raise SystemExit(3)
    got = dict(after["per"])
    if got != EXPECTED:
        print("STOP_PER_SYMBOL_MISMATCH", got)
        raise SystemExit(4)

    db = SessionLocal()
    replay_inserted = 0
    replay_skipped = 0
    replay_conflicts = 0
    try:
        for symbol in SYMBOLS:
            path = pick_file(symbol)
            content = path.read_bytes()
            preview = OhlcvService.parse_historical_file(db, content, path.name)
            req = OhlcvConfirmRequest(
                file_sha256=preview.file_sha256,
                original_filename=path.name,
                source_name="NSE",
                source_reference=f"manual_inputs/nse/Nifty50/{path.name}",
            )
            res = OhlcvService.confirm_import(db, req, content)
            replay_inserted += res["inserted"]
            replay_skipped += res["rows_duplicates"]
            replay_conflicts += res["rows_conflicts"]
            print("REPLAY", path.name, res)
    finally:
        db.close()

    conn = sqlite3.connect(PROD)
    conn.execute("PRAGMA foreign_keys=ON")
    after_replay = verify_quality(conn)
    snap2 = snapshot_ohlcv(conn)
    after_counts = counts(conn)
    print("REPLAY_INSERTED", replay_inserted)
    print("REPLAY_SKIPPED", replay_skipped)
    print("REPLAY_CONFLICTS", replay_conflicts)
    print("AFTER_REPLAY", after_replay)
    print("SNAPSHOT_UNCHANGED", snap1 == snap2)
    print("FINAL_COUNTS", after_counts)
    conn.close()

    if replay_inserted != 0 or replay_skipped != 2469 or after_replay["n"] != 2469 or snap1 != snap2:
        print("STOP_IDEMPOTENCY_FAILED")
        raise SystemExit(5)
    print("BATCH_A_IMPORT_OK")


if __name__ == "__main__":
    main()
