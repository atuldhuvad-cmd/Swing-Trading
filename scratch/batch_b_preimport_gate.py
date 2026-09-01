"""STEP 1 + STEP 2: new pre-import backup and the final pre-import gate.

Read-only with respect to production; the only write is the backup copy.
Exits non-zero on any gate failure.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
SRC = ROOT / "manual_inputs" / "nse" / "Nifty50"
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.models import StockMaster
from app.services.ohlcv_service import OhlcvService

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
EXPECTED_SESSIONS = 247
EXPECTED_STOCK_MASTER = 26
EXPECTED_OHLCV = 2469

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print("  GATE FAILURE:", msg)


def file_for(symbol: str) -> Path:
    return SRC / f"13-08-2025-TO-13-08-2026-{symbol}-ALL-N.csv"


def main() -> None:
    print("=== STEP 1 - NEW PRE-IMPORT BACKUP ===")
    pre_sha = hashlib.sha256(DB.read_bytes()).hexdigest()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB.parent / "safety_backups" / f"swing_trading_PRE_OHLCV_BATCH_B_{stamp}.db"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DB, backup)
    backup_sha = hashlib.sha256(backup.read_bytes()).hexdigest()

    bc = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    b_stocks = bc.execute("SELECT COUNT(*) FROM stock_master").fetchone()[0]
    b_ohlcv = bc.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0]
    b_integrity = bc.execute("PRAGMA integrity_check").fetchone()[0]
    b_fk = len(bc.execute("PRAGMA foreign_key_check").fetchall())
    bc.close()

    print("BACKUP_PATH          ", backup)
    print("BACKUP_SHA256        ", backup_sha)
    print("PRODUCTION_SHA256    ", pre_sha)
    print("SHA_IDENTICAL        ", backup_sha == pre_sha)
    print("BACKUP_STOCK_MASTER  ", b_stocks)
    print("BACKUP_OHLCV         ", b_ohlcv)
    print("BACKUP_INTEGRITY     ", b_integrity)
    print("BACKUP_FK_VIOLATIONS ", b_fk)

    if b_stocks != EXPECTED_STOCK_MASTER:
        fail(f"backup stock_master {b_stocks} != {EXPECTED_STOCK_MASTER}")
    if b_ohlcv != EXPECTED_OHLCV:
        fail(f"backup OHLCV {b_ohlcv} != {EXPECTED_OHLCV}")
    if b_integrity != "ok":
        fail(f"backup integrity_check = {b_integrity}")
    if b_fk:
        fail(f"backup foreign_key_check = {b_fk} violations")
    if backup_sha != pre_sha:
        fail("backup SHA-256 differs from production")
    if failures:
        print("\nABORTING BEFORE ANY GATE WORK")
        raise SystemExit(1)

    print("\n=== STEP 2a - STOCK MASTER PRESENCE ===")
    db = SessionLocal()
    stock_ids: dict[str, int] = {}
    try:
        for sym in EXPECTED_SHA:
            rows = db.query(StockMaster).filter(StockMaster.nse_symbol == sym).all()
            if len(rows) != 1:
                fail(f"{sym} appears {len(rows)} times in stock_master")
                continue
            stock_ids[sym] = rows[0].stock_id
            print(f"  {sym:<12} exactly once, stock_id={rows[0].stock_id}")

        print("\n=== STEP 2b - SHA-256 RECOMPUTATION ===")
        contents: dict[str, bytes] = {}
        for sym, want in EXPECTED_SHA.items():
            path = file_for(sym)
            if not path.exists():
                fail(f"{sym} file missing: {path.name}")
                continue
            data = path.read_bytes()
            got = hashlib.sha256(data).hexdigest()
            match = got == want
            contents[sym] = data
            print(f"  {sym:<12} {'MATCH  ' if match else 'MISMATCH'} {got}")
            if not match:
                fail(f"{sym} SHA-256 mismatch (expected {want}, got {got})")

        if failures:
            print("\nABORTING BEFORE PREVIEW")
            raise SystemExit(1)

        print("\n=== STEP 2c - NON-PERSISTENT PREVIEW ===")
        totals = {k: 0 for k in ("physical", "eq", "ignored", "accepted", "rejected",
                                 "duplicates", "conflicts", "unmapped")}
        per_symbol = {}
        sma_ready = 0
        for sym, data in contents.items():
            preview = OhlcvService.parse_historical_file(db, data, file_for(sym).name)
            dates = sorted({r.trading_date for r in preview.preview_rows
                            if r.status == "ACCEPTED" and r.trading_date})
            sessions = len(dates)
            eq = preview.rows_received - preview.rows_ignored
            per_symbol[sym] = {
                "physical": preview.rows_received, "eq": eq,
                "ignored": preview.rows_ignored, "accepted": preview.rows_accepted,
                "rejected": preview.rows_rejected, "duplicates": preview.rows_duplicates,
                "conflicts": preview.rows_conflicts, "unmapped": preview.rows_unmapped,
                "sessions": sessions, "earliest": dates[0] if dates else None,
                "latest": dates[-1] if dates else None,
            }
            totals["physical"] += preview.rows_received
            totals["eq"] += eq
            totals["ignored"] += preview.rows_ignored
            totals["accepted"] += preview.rows_accepted
            totals["rejected"] += preview.rows_rejected
            totals["duplicates"] += preview.rows_duplicates
            totals["conflicts"] += preview.rows_conflicts
            totals["unmapped"] += preview.rows_unmapped
            if sessions >= 200:
                sma_ready += 1

            print(f"  {sym:<12} eq={eq} accepted={preview.rows_accepted} "
                  f"unmapped={preview.rows_unmapped} invalid={preview.rows_rejected} "
                  f"dup={preview.rows_duplicates} conf={preview.rows_conflicts} "
                  f"sessions={sessions} {dates[0] if dates else '-'}..{dates[-1] if dates else '-'}")

            if sessions != EXPECTED_SESSIONS:
                fail(f"{sym} sessions {sessions} != {EXPECTED_SESSIONS}")
            if preview.rows_accepted != EXPECTED_SESSIONS:
                fail(f"{sym} accepted {preview.rows_accepted} != {EXPECTED_SESSIONS}")
            for key in ("rows_unmapped", "rows_rejected", "rows_duplicates", "rows_conflicts"):
                if getattr(preview, key):
                    fail(f"{sym} {key} = {getattr(preview, key)}")
    finally:
        db.rollback()
        db.close()

    print("\nTOTALS", json.dumps(totals))
    print("FILES", len(contents), "SMA200_READY", f"{sma_ready}/{len(EXPECTED_SHA)}")

    if len(contents) != 10:
        fail(f"files = {len(contents)} != 10")
    if totals["eq"] != 2470:
        fail(f"EQ rows {totals['eq']} != 2470")
    if totals["accepted"] != 2470:
        fail(f"accepted {totals['accepted']} != 2470")
    if sma_ready != 10:
        fail(f"SMA200-ready {sma_ready}/10")

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    prod_ohlcv = conn.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0]
    prod_stocks = conn.execute("SELECT COUNT(*) FROM stock_master").fetchone()[0]
    conn.close()
    print("PRODUCTION_AFTER_PREVIEW ohlcv=", prod_ohlcv, "stock_master=", prod_stocks)
    if prod_ohlcv != EXPECTED_OHLCV or prod_stocks != EXPECTED_STOCK_MASTER:
        fail("preview caused production drift")

    state = {"backup_path": str(backup), "backup_sha256": backup_sha,
             "production_pre_import_sha256": pre_sha, "backup_stock_master": b_stocks,
             "backup_ohlcv": b_ohlcv, "backup_integrity": b_integrity,
             "backup_fk_violations": b_fk, "stock_ids": stock_ids,
             "totals": totals, "per_symbol": per_symbol}
    out = ROOT / "manual_inputs" / "batch_b" / f"batch_b_preimport_gate_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("GATE_REPORT", out)

    if failures:
        print("\nGATE FAILED:", failures)
        raise SystemExit(1)
    print("\nGATE PASSED - SAFE TO IMPORT")


if __name__ == "__main__":
    main()
