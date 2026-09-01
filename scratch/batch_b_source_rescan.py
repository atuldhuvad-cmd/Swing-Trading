"""Batch B source re-scan. Read-only: never writes to the production database."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
DB = ROOT / "data" / "swing_trading.db"
OUT_DIR = ROOT / "manual_inputs" / "batch_b"

SEARCH_ROOTS = [
    ROOT / "manual_inputs",
    ROOT / "data",
    Path(r"C:\Users\dhuva\Downloads"),
    Path(r"C:\Users\dhuva\Desktop"),
    Path(r"D:\Downloads"),
]

BATCH_B = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]
MIN_SESSIONS = 200
EXPECTED = {
    "daily_ohlcv": 2469, "candidate_evaluation_run": 33, "candidate_criterion_result": 297,
    "risk_reward_result": 29, "fundamental_snapshot": 10, "broker_recommendation": 5,
}


def production_state() -> dict:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        state = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in EXPECTED}
        state["synthetic_ohlcv"] = conn.execute(
            "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
        ).fetchone()[0]
        state["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        state["fk_violations"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()
    return state


def is_quote_slb(name: str) -> bool:
    return "quote-slb" in name.lower().replace(" ", "")


def scan_file(path: Path) -> dict:
    content = path.read_bytes()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers

    physical = non_eq = bad_eq = 0
    eq_dates: list = []
    symbols: set[str] = set()
    series_counts: dict[str, int] = defaultdict(int)

    for row in reader:
        physical += 1
        series = (row.get("Series") or "").strip().strip('"').upper()
        sym = (row.get("Symbol") or "").strip().strip('"').upper()
        if sym:
            symbols.add(sym)
        series_counts[series or "?"] += 1
        if series != "EQ":
            non_eq += 1
            continue
        raw = (row.get("Date") or "").strip().strip('"')
        parsed = None
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%B-%Y", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(raw, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            bad_eq += 1
        else:
            eq_dates.append(parsed)

    sessions = sorted(set(eq_dates))
    return {
        "path": str(path),
        "filename": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "physical_rows": physical,
        "eq_rows": len(eq_dates) + bad_eq,
        "non_eq_filtered": non_eq,
        "invalid_eq": bad_eq,
        "duplicate_eq_dates": len(eq_dates) - len(sessions),
        "valid_sessions": len(sessions),
        "earliest": str(sessions[0]) if sessions else None,
        "latest": str(sessions[-1]) if sessions else None,
        "span_months": round((sessions[-1] - sessions[0]).days / 30.44, 1) if sessions else None,
        "symbols": sorted(symbols),
        "series_counts": dict(series_counts),
        "is_quote_slb": is_quote_slb(path.name),
    }


def main() -> None:
    before = production_state()

    searched, csvs = [], []
    for base in SEARCH_ROOTS:
        if not base.exists():
            searched.append(f"{base}  [ABSENT]")
            continue
        found = [p for p in base.rglob("*.csv") if "node_modules" not in str(p)]
        searched.append(f"{base}  [{len(found)} csv]")
        csvs.extend(found)

    print("=== DIRECTORIES SEARCHED ===")
    for s in searched:
        print("  " + s)

    slb = [p for p in csvs if is_quote_slb(p.name)]
    cash = [p for p in csvs if not is_quote_slb(p.name)]
    print(f"\nTotal CSVs: {len(csvs)} | Quote-SLB rejected: {len(slb)} | cash-market candidates: {len(cash)}")

    scans = {}
    for p in cash:
        try:
            scans[str(p)] = scan_file(p)
        except Exception as exc:
            print(f"  UNREADABLE {p}: {exc}")

    rows = []
    for symbol in BATCH_B:
        matches = [s for s in scans.values()
                   if symbol in s["symbols"] or f"-{symbol}-" in s["filename"].upper()]
        slb_hits = [p.name for p in slb if f"-{symbol}-" in p.name.upper()]
        if not matches:
            rows.append({
                "symbol": symbol, "file": None, "date_range": None, "physical_rows": 0,
                "eq_rows": 0, "non_eq_filtered": 0, "valid_sessions": 0, "ge_200": False,
                "sma200_ready": False, "sha256": None, "quote_slb_seen": slb_hits,
                "status": "MISSING - USER DOWNLOAD REQUIRED",
            })
            continue

        best = max(matches, key=lambda s: s["valid_sessions"])
        identity_ok = best["symbols"] == [symbol]
        ge200 = best["valid_sessions"] >= MIN_SESSIONS
        if not identity_ok:
            status = f"REJECTED - symbol identity mismatch {best['symbols']}"
        elif ge200:
            status = "READY"
        else:
            status = f"INSUFFICIENT - {best['valid_sessions']} sessions ({MIN_SESSIONS - best['valid_sessions']} short)"
        rows.append({
            "symbol": symbol, "file": best["filename"], "path": best["path"],
            "date_range": f"{best['earliest']} to {best['latest']}",
            "span_months": best["span_months"], "physical_rows": best["physical_rows"],
            "eq_rows": best["eq_rows"], "non_eq_filtered": best["non_eq_filtered"],
            "invalid_eq": best["invalid_eq"], "duplicate_eq_dates": best["duplicate_eq_dates"],
            "valid_sessions": best["valid_sessions"], "ge_200": ge200, "sma200_ready": ge200,
            "sha256": best["sha256"], "symbol_identity_ok": identity_ok,
            "other_files_not_merged": [m["filename"] for m in matches if m["path"] != best["path"]],
            "quote_slb_seen": slb_hits, "status": status,
        })

    after = production_state()

    print("\n=== BATCH B SOURCE STATE ===")
    for r in rows:
        print(f"\n{r['symbol']}")
        print(f"  File            : {r['file'] or 'NONE'}")
        print(f"  Date range      : {r['date_range'] or '-'}"
              + (f"  ({r.get('span_months')} months)" if r.get("span_months") else ""))
        print(f"  Physical rows   : {r['physical_rows']}")
        print(f"  EQ rows         : {r['eq_rows']}")
        print(f"  Non-EQ filtered : {r['non_eq_filtered']}")
        print(f"  Valid sessions  : {r['valid_sessions']}")
        print(f"  >=200           : {r['ge_200']}")
        print(f"  SMA200-ready    : {r['sma200_ready']}")
        print(f"  SHA-256         : {r['sha256'] or '-'}")
        print(f"  Status          : {r['status']}")
        if r.get("other_files_not_merged"):
            print(f"  Not merged      : {r['other_files_not_merged']}")

    ready = sum(1 for r in rows if r["status"] == "READY")
    print(f"\nREADY {ready}/{len(BATCH_B)}")
    print("PRODUCTION_BEFORE", json.dumps(before))
    print("PRODUCTION_AFTER ", json.dumps(after))
    print("PRODUCTION_DRIFT", json.dumps({k: (before[k], after[k]) for k in before if before[k] != after[k]}))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"batch_b_source_rescan_{stamp}.json"
    out.write_text(json.dumps(
        {"generated_at": stamp, "searched": searched, "rows": rows,
         "production_before": before, "production_after": after}, indent=2), encoding="utf-8")
    print("REPORT", out)


if __name__ == "__main__":
    main()
