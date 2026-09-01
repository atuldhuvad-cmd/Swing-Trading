"""Register the nine missing Batch B stocks via the existing POST /api/stocks workflow.

Metadata is derived from the authoritative NSE constituent list, following the Batch A
convention: NSE "Industry" is stored in `sector`; industry / market_cap_category /
bse_symbol are left null; listing_status defaults to ACTIVE.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8000/api/stocks"
DB = Path(r"D:\Swing Trading\data\swing_trading.db")
NIFTY_LIST = Path(r"D:\Swing Trading\manual_inputs\nifty50\ind_nifty50list.csv")

TO_REGISTER = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
               "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE"]
MUST_NOT_REGISTER = "HINDALCO"


def api_get(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def api_post(url: str, payload: dict):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> None:
    metadata = {}
    with NIFTY_LIST.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            metadata[row["Symbol"].strip().upper()] = {
                "company_name": row["Company Name"].strip(),
                "sector": row["Industry"].strip(),
                "isin": row["ISIN Code"].strip().upper(),
            }

    missing_meta = [s for s in TO_REGISTER if s not in metadata]
    if missing_meta:
        raise SystemExit(f"STOP: no authoritative metadata for {missing_meta}")

    existing = api_get(f"{API}?limit=500")
    existing_syms = {s["nse_symbol"] for s in existing}
    print(f"stock_master before (via API): {len(existing)}")
    print("HINDALCO present before:", MUST_NOT_REGISTER in existing_syms)

    already = [s for s in TO_REGISTER if s in existing_syms]
    if already:
        raise SystemExit(f"STOP: already registered, refusing to duplicate: {already}")

    before_ids = {s["nse_symbol"]: s["stock_id"] for s in existing}

    results = []
    for sym in TO_REGISTER:
        meta = metadata[sym]
        payload = {
            "nse_symbol": sym,
            "company_name": meta["company_name"],
            "isin": meta["isin"],
            "sector": meta["sector"],
            "listing_status": "ACTIVE",
        }
        status, body = api_post(API, payload)
        ok = status == 200
        results.append({"symbol": sym, "http_status": status, "ok": ok,
                        "payload": payload, "response": body})
        print(f"  {sym:<12} HTTP {status} "
              + (f"-> stock_id={body.get('stock_id')}" if ok else f"-> {body}"))

    after = api_get(f"{API}?limit=500")
    after_syms = [s["nse_symbol"] for s in after]
    print(f"\nstock_master after (via API): {len(after)}")

    print("\n=== VERIFICATION ===")
    dupes = {s: after_syms.count(s) for s in set(after_syms) if after_syms.count(s) > 1}
    print("Duplicate symbols:", dupes or "none")
    print("HINDALCO occurrences:", after_syms.count(MUST_NOT_REGISTER))

    unchanged = True
    for s in after:
        if s["nse_symbol"] in before_ids and before_ids[s["nse_symbol"]] != s["stock_id"]:
            unchanged = False
            print(f"  CHANGED ID: {s['nse_symbol']}")
    print("Pre-existing stock IDs unchanged:", unchanged)

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    print("\n=== NEW ROWS IN DB ===")
    q = ",".join("?" * len(TO_REGISTER))
    for r in conn.execute(f"SELECT * FROM stock_master WHERE nse_symbol IN ({q}) ORDER BY stock_id", TO_REGISTER):
        d = dict(r)
        print(f"  id={d['stock_id']:<4} {d['nse_symbol']:<12} {d['company_name']:<40} "
              f"isin={d['isin']} sector={d['sector']} status={d['listing_status']}")
    print("\nstock_master count (DB):", conn.execute("SELECT COUNT(*) FROM stock_master").fetchone()[0])
    print("daily_ohlcv:", conn.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0])
    print("candidate_evaluation_run:", conn.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0])
    print("integrity:", conn.execute("PRAGMA integrity_check").fetchone()[0])
    print("fk_violations:", len(conn.execute("PRAGMA foreign_key_check").fetchall()))
    conn.close()

    created = sum(1 for r in results if r["ok"])
    print(f"\nCREATED {created}/{len(TO_REGISTER)}")


if __name__ == "__main__":
    main()
