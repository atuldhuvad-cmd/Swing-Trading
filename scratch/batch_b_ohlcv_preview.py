"""Batch B OHLCV location + NON-PERSISTENT preview through the real application parser.

Performs zero production writes: the session is rolled back and never committed.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal
from app.services.ohlcv_service import OhlcvService

SYMBOLS = [
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
]
SEARCH_DIRS = [ROOT / "manual_inputs", ROOT / "data", ROOT / "scratch"]
MIN_SESSIONS = 200
SYNTHETIC_SQL = (
    "SELECT COUNT(*) FROM daily_ohlcv "
    "WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
)


def counts(conn: sqlite3.Connection) -> dict:
    out = {}
    for t in [
        "daily_ohlcv",
        "candidate_evaluation_run",
        "candidate_criterion_result",
        "risk_reward_result",
        "fundamental_snapshot",
        "broker_recommendation",
        "data_import_batch",
        "stock_master",
    ]:
        out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    out["synthetic_ohlcv"] = conn.execute(SYNTHETIC_SQL).fetchone()[0]
    out["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    out["fk"] = conn.execute("PRAGMA foreign_key_check").fetchall()
    return out


def find_candidates(symbol: str) -> list[Path]:
    hits: list[Path] = []
    for base in SEARCH_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.csv"):
            name = path.name.upper()
            if f"-{symbol}-" in name or name.startswith(symbol + "-") or f"_{symbol}_" in name:
                hits.append(path)
    return sorted(set(hits), key=lambda p: p.name)


def classify(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    usable, slb = [], []
    for p in paths:
        if "quote-slb" in p.name.lower().replace(" ", ""):
            slb.append(p)
        else:
            usable.append(p)
    return usable, slb


def eq_stats(content: bytes) -> dict:
    import csv
    import io

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers
    physical = 0
    eq_dates = []
    non_eq = 0
    symbols = set()
    for row in reader:
        physical += 1
        series = (row.get("Series") or row.get("Series  ") or "").strip().strip('"')
        sym = (row.get("Symbol") or row.get("Symbol  ") or "").strip().strip('"')
        if sym:
            symbols.add(sym.upper())
        if series.upper() != "EQ":
            non_eq += 1
            continue
        raw = (row.get("Date") or row.get("Date  ") or "").strip().strip('"')
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d/%m/%Y"):
            try:
                eq_dates.append(datetime.strptime(raw, fmt).date())
                break
            except ValueError:
                continue
    return {
        "physical_rows": physical,
        "eq_rows": len(eq_dates),
        "non_eq_rows": non_eq,
        "unique_eq_sessions": len(set(eq_dates)),
        "earliest_eq_date": str(min(eq_dates)) if eq_dates else None,
        "latest_eq_date": str(max(eq_dates)) if eq_dates else None,
        "file_symbols": sorted(symbols),
    }


def main() -> None:
    conn = sqlite3.connect(str(DB))
    before = counts(conn)
    conn.close()
    print("COUNTS_BEFORE", json.dumps(before, default=str))
    if before["integrity"] != "ok" or before["fk"]:
        raise SystemExit("STOP_INTEGRITY_BEFORE")

    db = SessionLocal()
    reports = []
    totals = defaultdict(int)
    try:
        for symbol in SYMBOLS:
            found = find_candidates(symbol)
            usable, slb = classify(found)
            entry = {
                "symbol": symbol,
                "files_found": [str(p.relative_to(ROOT)) for p in found],
                "quote_slb_rejected": [str(p.relative_to(ROOT)) for p in slb],
                "previewed": None,
                "status": "MISSING_FILE",
            }
            if not usable:
                reports.append(entry)
                continue

            chosen = sorted(usable, key=lambda p: (p.stat().st_size, p.name))[-1]
            content = chosen.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            stats = eq_stats(content)
            identity_ok = stats["file_symbols"] == [symbol]

            preview = OhlcvService.parse_historical_file(db, content, chosen.name)
            eq_seen = (
                preview.rows_accepted
                + preview.rows_rejected
                + preview.rows_unmapped
                + preview.rows_duplicates
                + preview.rows_conflicts
            )
            sessions = stats["unique_eq_sessions"]
            entry.update({
                "previewed": {
                    "filename": chosen.name,
                    "path": str(chosen.relative_to(ROOT)),
                    "sha256": sha,
                    "physical_rows": stats["physical_rows"],
                    "eq_rows": stats["eq_rows"],
                    "non_eq_filtered": preview.rows_ignored,
                    "parser_eq_rows": eq_seen,
                    "invalid_eq": preview.rows_rejected,
                    "unmapped": preview.rows_unmapped,
                    "duplicates": preview.rows_duplicates,
                    "conflicts": preview.rows_conflicts,
                    "accepted": preview.rows_accepted,
                    "earliest_date": stats["earliest_eq_date"],
                    "latest_date": stats["latest_eq_date"],
                    "unique_eq_sessions": sessions,
                    "file_symbols": stats["file_symbols"],
                    "symbol_identity_ok": identity_ok,
                    "sma200_ready": sessions >= MIN_SESSIONS,
                },
                "status": "OK" if (sessions >= MIN_SESSIONS and identity_ok) else "INSUFFICIENT_SESSIONS",
            })
            totals["files_previewed"] += 1
            totals["physical_rows"] += stats["physical_rows"]
            totals["eq_rows"] += stats["eq_rows"]
            totals["non_eq_filtered"] += preview.rows_ignored
            totals["invalid_eq"] += preview.rows_rejected
            totals["unmapped"] += preview.rows_unmapped
            totals["duplicates"] += preview.rows_duplicates
            totals["conflicts"] += preview.rows_conflicts
            if sessions >= MIN_SESSIONS:
                totals["stocks_ge_200"] += 1
            reports.append(entry)
    finally:
        db.rollback()
        db.close()

    conn = sqlite3.connect(str(DB))
    after = counts(conn)
    conn.close()
    print("COUNTS_AFTER", json.dumps(after, default=str))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = {
        "generated_at": stamp,
        "min_sessions_required": MIN_SESSIONS,
        "before": before,
        "after": after,
        "totals": dict(totals),
        "reports": reports,
    }
    out_path = ROOT / "manual_inputs" / "batch_b" / f"batch_b_ohlcv_preview_{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("REPORT", str(out_path))

    for r in reports:
        p = r["previewed"]
        if p:
            print(
                "STOCK", r["symbol"], r["status"], p["filename"],
                "physical", p["physical_rows"], "eq", p["eq_rows"],
                "non_eq", p["non_eq_filtered"], "invalid", p["invalid_eq"],
                "dup", p["duplicates"], "conflict", p["conflicts"],
                "range", p["earliest_date"], "->", p["latest_date"],
                "sessions", p["unique_eq_sessions"], "sma200", p["sma200_ready"],
                "sha", p["sha256"][:16],
            )
        else:
            print("STOCK", r["symbol"], r["status"], "found", r["files_found"], "slb_rejected", r["quote_slb_rejected"])
    print("TOTALS", json.dumps(dict(totals)))

    writes = {k: (before[k], after[k]) for k in before if k not in ("integrity", "fk") and before[k] != after[k]}
    print("PRODUCTION_DELTA", json.dumps(writes))
    print("INTEGRITY_AFTER", after["integrity"], "FK_AFTER", after["fk"])
    if writes:
        raise SystemExit("STOP_PRODUCTION_WRITE_DETECTED")


if __name__ == "__main__":
    main()
