"""Read-only inspection of fundamental schema, provenance, and Batch A classification precedent."""
from __future__ import annotations

import sqlite3

SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]

conn = sqlite3.connect("file:D:/Swing Trading/data/swing_trading.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

print("=== fundamental_snapshot columns ===")
print([r["name"] for r in conn.execute("PRAGMA table_info(fundamental_snapshot)")])
print("\n=== fundamental_metric columns ===")
print([r["name"] for r in conn.execute("PRAGMA table_info(fundamental_metric)")])

print("\n=== EXISTING SNAPSHOTS (Batch A precedent) ===")
for r in conn.execute(
    "SELECT f.*, s.nse_symbol FROM fundamental_snapshot f "
    "JOIN stock_master s ON s.stock_id = f.stock_id ORDER BY f.snapshot_id"
):
    d = dict(r)
    print(f"\n  {d['nse_symbol']} (snapshot {d['snapshot_id']})")
    for k, v in d.items():
        if k not in ("nse_symbol", "snapshot_id"):
            print(f"    {k}: {v}")

print("\n=== REVENUE METRICS RECORDED ===")
for r in conn.execute(
    "SELECT s.nse_symbol, m.metric_name, m.metric_value, m.status "
    "FROM fundamental_metric m JOIN fundamental_snapshot f ON f.snapshot_id = m.snapshot_id "
    "JOIN stock_master s ON s.stock_id = f.stock_id WHERE m.metric_name = 'revenue' "
    "ORDER BY s.nse_symbol"
):
    print(" ", dict(r))

print("\n=== BATCH B STOCK METADATA ===")
q = ",".join("?" * len(SYMBOLS))
for r in conn.execute(
    f"SELECT stock_id, nse_symbol, company_name, isin, sector, industry, "
    f"market_cap_category, listing_status FROM stock_master WHERE nse_symbol IN ({q}) "
    f"ORDER BY nse_symbol", SYMBOLS
):
    d = dict(r)
    print(f"  {d['nse_symbol']:<12} id={d['stock_id']:<3} {d['company_name']:<38} "
          f"isin={d['isin']} sector={d['sector']}")

print("\n=== BATCH B EXISTING FUNDAMENTAL SNAPSHOTS ===")
rows = list(conn.execute(
    f"SELECT s.nse_symbol, COUNT(f.snapshot_id) n FROM stock_master s "
    f"LEFT JOIN fundamental_snapshot f ON f.stock_id = s.stock_id "
    f"WHERE s.nse_symbol IN ({q}) GROUP BY s.nse_symbol ORDER BY s.nse_symbol", SYMBOLS))
for r in rows:
    print(f"  {r['nse_symbol']:<12} snapshots={r['n']}")
conn.close()
