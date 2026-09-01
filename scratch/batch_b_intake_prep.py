"""Batch B intake preparation: read-only scan of the NSE intake folder + checklist generation.

Zero database writes. Opens the production DB read-only purely to assert counts are unchanged.
"""
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
INTAKE = ROOT / "manual_inputs" / "nse" / "Nifty50"
OUT_DIR = ROOT / "manual_inputs" / "batch_b"

BATCH_B = [
    "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO",
]
MIN_SESSIONS = 200
EXPECTED = {
    "daily_ohlcv": 2469,
    "candidate_evaluation_run": 33,
    "candidate_criterion_result": 297,
    "risk_reward_result": 29,
    "fundamental_snapshot": 10,
    "broker_recommendation": 5,
}
SYNTHETIC_SQL = (
    "SELECT COUNT(*) FROM daily_ohlcv "
    "WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
)


def production_state() -> dict:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        state = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in EXPECTED}
        state["synthetic_ohlcv"] = conn.execute(SYNTHETIC_SQL).fetchone()[0]
        state["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        state["fk_violations"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()
    return state


def is_quote_slb(name: str) -> bool:
    return "quote-slb" in name.lower().replace(" ", "")


def scan(path: Path) -> dict:
    content = path.read_bytes()
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers

    physical = 0
    non_eq = 0
    eq_dates: list = []
    bad_eq = 0
    symbols = set()
    series_seen: dict[str, int] = defaultdict(int)

    for row in reader:
        physical += 1
        series = (row.get("Series") or "").strip().strip('"').upper()
        sym = (row.get("Symbol") or "").strip().strip('"').upper()
        if sym:
            symbols.add(sym)
        series_seen[series or "?"] += 1
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
    span_months = None
    if sessions:
        span_months = round((sessions[-1] - sessions[0]).days / 30.44, 1)

    return {
        "filename": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "physical_rows": physical,
        "eq_rows": len(eq_dates) + bad_eq,
        "non_eq_rows": non_eq,
        "invalid_eq": bad_eq,
        "valid_sessions": len(sessions),
        "duplicate_eq_dates": len(eq_dates) - len(sessions),
        "earliest": str(sessions[0]) if sessions else None,
        "latest": str(sessions[-1]) if sessions else None,
        "span_months": span_months,
        "symbols": sorted(symbols),
        "series_breakdown": dict(series_seen),
        "quote_slb": is_quote_slb(path.name),
    }


def main() -> None:
    before = production_state()

    all_files = sorted(INTAKE.glob("*.csv"))
    slb_files = [p for p in all_files if is_quote_slb(p.name)]
    cash_files = [p for p in all_files if not is_quote_slb(p.name)]

    scans = {p.name: scan(p) for p in cash_files}

    reference = []
    checklist = []
    for symbol in BATCH_B:
        matches = [
            s for s in scans.values()
            if symbol in s["symbols"] or f"-{symbol}-" in s["filename"].upper()
        ]
        slb_for_symbol = [p.name for p in slb_files if f"-{symbol}-" in p.name.upper()]
        if not matches:
            checklist.append({
                "symbol": symbol,
                "file_located": None,
                "date_range": None,
                "physical_rows": 0,
                "eq_rows": 0,
                "non_eq_rows": 0,
                "valid_sessions": 0,
                "ge_200": False,
                "sma200_ready": False,
                "quote_slb_present": slb_for_symbol,
                "status": "MISSING - USER DOWNLOAD REQUIRED",
            })
            continue

        best = max(matches, key=lambda s: s["valid_sessions"])
        others = [m["filename"] for m in matches if m["filename"] != best["filename"]]
        identity_ok = best["symbols"] == [symbol]
        ge200 = best["valid_sessions"] >= MIN_SESSIONS
        if not identity_ok:
            status = "REJECTED — SYMBOL IDENTITY MISMATCH"
        elif ge200:
            status = "READY"
        else:
            status = (
                f"INSUFFICIENT - {best['valid_sessions']} sessions "
                f"({MIN_SESSIONS - best['valid_sessions']} short) - LONGER EXPORT REQUIRED"
            )
        checklist.append({
            "symbol": symbol,
            "file_located": best["filename"],
            "sha256": best["sha256"],
            "date_range": f"{best['earliest']} to {best['latest']}",
            "span_months": best["span_months"],
            "physical_rows": best["physical_rows"],
            "eq_rows": best["eq_rows"],
            "non_eq_rows": best["non_eq_rows"],
            "invalid_eq": best["invalid_eq"],
            "duplicate_eq_dates": best["duplicate_eq_dates"],
            "valid_sessions": best["valid_sessions"],
            "ge_200": ge200,
            "sma200_ready": ge200,
            "symbol_identity_ok": identity_ok,
            "other_overlapping_exports_not_merged": others,
            "quote_slb_present": slb_for_symbol,
            "status": status,
        })

    # Reference coverage from the already-imported Batch A full-year exports.
    for s in scans.values():
        if s["valid_sessions"] >= MIN_SESSIONS:
            reference.append({
                "filename": s["filename"],
                "range": f"{s['earliest']} to {s['latest']}",
                "span_months": s["span_months"],
                "valid_sessions": s["valid_sessions"],
            })
    reference.sort(key=lambda r: r["filename"])

    after = production_state()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": stamp,
        "intake_folder": str(INTAKE),
        "min_sessions_required": MIN_SESSIONS,
        "files_in_folder": len(all_files),
        "cash_market_files": len(cash_files),
        "quote_slb_files_rejected": [p.name for p in slb_files],
        "checklist": checklist,
        "reference_full_year_exports": reference,
        "production_before": before,
        "production_after": after,
    }
    (OUT_DIR / f"batch_b_intake_checklist_{stamp}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    print("PRODUCTION_BEFORE", json.dumps(before))
    print("PRODUCTION_AFTER", json.dumps(after))
    drift = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    print("PRODUCTION_DRIFT", json.dumps(drift))
    print("EXPECTED_MATCH", all(before[k] == v for k, v in EXPECTED.items()))
    print("SLB_REJECTED", len(slb_files))
    print()
    for c in checklist:
        print(
            f"{c['symbol']:<10} file={c['file_located'] or 'NONE':<45} "
            f"range={c['date_range'] or '-':<26} phys={c['physical_rows']:<5} "
            f"eq={c['eq_rows']:<5} nonEQ={c['non_eq_rows']:<4} sess={c['valid_sessions']:<5} "
            f">=200={str(c['ge_200']):<5} sma200={str(c['sma200_ready']):<5} {c['status']}"
        )
    print()
    print("REFERENCE_FULL_YEAR_EXPORTS")
    for r in reference:
        print(f"  {r['filename']:<48} {r['range']}  months={r['span_months']}  sessions={r['valid_sessions']}")
    ready = sum(1 for c in checklist if c["status"] == "READY")
    print(f"\nREADY {ready}/{len(BATCH_B)}")
    print("CHECKLIST_JSON", str(OUT_DIR / f"batch_b_intake_checklist_{stamp}.json"))


if __name__ == "__main__":
    main()
