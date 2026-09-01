"""Read-only forensic verification of the Swing Trading production baseline."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path(r"D:\Swing Trading\data\swing_trading.db")
FINGERPRINT = "146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe"
BATCH_B = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]
EXPECTED = {
    "daily_ohlcv": 2469,
    "fundamental_snapshot": 10,
    "candidate_evaluation_run": 33,
    "candidate_criterion_result": 297,
    "risk_reward_result": 29,
    "broker_recommendation": 5,
}

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

print("=== COUNTS vs EXPECTED BASELINE ===")
counts = {}
for table, expected in EXPECTED.items():
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    counts[table] = n
    print(f"{table:<30} {n:<8} expected {expected:<8} {'MATCH' if n == expected else 'MISMATCH'}")

print("\n=== SYNTHETIC DATA CHECKS ===")
synth_exact = conn.execute(
    "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
).fetchone()[0]
synth_round = conn.execute(
    "SELECT COUNT(*) FROM daily_ohlcv WHERE open=high AND high=low AND low=close"
).fetchone()[0]
synth_zero = conn.execute(
    "SELECT COUNT(*) FROM daily_ohlcv WHERE volume IS NULL OR volume<=0 OR close<=0"
).fetchone()[0]
print(f"classic synthetic pattern      {synth_exact}")
print(f"flat OHLC (open=high=low=close) {synth_round}")
print(f"non-positive volume/close       {synth_zero}")

print("\n=== LATEST CLASSIFICATIONS ===")
cols = [r["name"] for r in conn.execute("PRAGMA table_info(candidate_evaluation_run)")]
print("run columns:", cols)
fp_col = next((c for c in cols if "fingerprint" in c.lower()), None)
cls_col = next((c for c in cols if "classif" in c.lower() or c.lower() in ("status", "result")), None)
print(f"fingerprint column: {fp_col}   classification column: {cls_col}")

pk_col = next((r["name"] for r in conn.execute("PRAGMA table_info(candidate_evaluation_run)") if r["pk"]), "rowid")
rows = conn.execute(f"SELECT * FROM candidate_evaluation_run ORDER BY {pk_col} DESC LIMIT 10").fetchall()
latest_ids = sorted(r[pk_col] for r in rows)
print("latest 10 run ids:", latest_ids)
tally: dict[str, int] = {}
fps = set()
for r in rows:
    tally[r[cls_col]] = tally.get(r[cls_col], 0) + 1
    if fp_col:
        fps.add(r[fp_col])
print("classification tally (latest 10 runs):", json.dumps(tally))
print("fingerprints in latest 10 runs:", fps)
print("fingerprint preserved:", FINGERPRINT in fps)

print("\n=== ALL DISTINCT FINGERPRINTS IN DB ===")
if fp_col:
    for r in conn.execute(f"SELECT {fp_col} AS fp, COUNT(*) AS n FROM candidate_evaluation_run GROUP BY {fp_col}"):
        print(f"  {r['fp']}  x{r['n']}")

print("\n=== BATCH B CONTAMINATION CHECK ===")
stock_cols = [r["name"] for r in conn.execute("PRAGMA table_info(stock_master)")]
sym_col = "symbol" if "symbol" in stock_cols else stock_cols[1]
stock_pk = next((r["name"] for r in conn.execute("PRAGMA table_info(stock_master)") if r["pk"]), "rowid")
contaminated = []
for sym in BATCH_B:
    row = conn.execute(
        f"SELECT s.{stock_pk} AS sid, s.{sym_col} AS sym, "
        f"(SELECT COUNT(*) FROM daily_ohlcv o WHERE o.stock_id=s.{stock_pk}) AS n "
        f"FROM stock_master s WHERE UPPER(s.{sym_col})=?", (sym,)
    ).fetchone()
    if row is None:
        print(f"{sym:<12} not in stock_master")
    else:
        print(f"{sym:<12} stock_id={row['sid']:<4} ohlcv_rows={row['n']}")
        if row["n"]:
            contaminated.append((sym, row["n"]))
print("Batch B OHLCV contamination:", contaminated if contaminated else "NONE")

print("\n=== OHLCV COVERAGE BY SYMBOL ===")
ohlcv_date = next((r["name"] for r in conn.execute("PRAGMA table_info(daily_ohlcv)")
                   if "date" in r["name"].lower()), "trade_date")
for r in conn.execute(
    f"SELECT s.{sym_col} AS sym, COUNT(*) AS n, MIN(o.{ohlcv_date}) AS lo, MAX(o.{ohlcv_date}) AS hi "
    f"FROM stock_master s JOIN daily_ohlcv o ON o.stock_id=s.{stock_pk} "
    f"GROUP BY s.{stock_pk} ORDER BY s.{sym_col}"
):
    print(f"  {r['sym']:<12} {r['n']:<6} {r['lo']} -> {r['hi']}")

print("\n=== IMPORT BATCHES (most recent 5) ===")
batch_pk = next((r["name"] for r in conn.execute("PRAGMA table_info(data_import_batch)") if r["pk"]), "rowid")
for r in conn.execute(f"SELECT * FROM data_import_batch ORDER BY {batch_pk} DESC LIMIT 5"):
    d = dict(r)
    print("  ", {k: d[k] for k in list(d)[:7]})

print("\n=== PRAGMA CHECKS ===")
print("integrity_check:", conn.execute("PRAGMA integrity_check").fetchone()[0])
fk = conn.execute("PRAGMA foreign_key_check").fetchall()
print("foreign_key_check violations:", len(fk))
if fk:
    print("  ", fk[:10])

conn.close()
