"""Read-only check of corporate-action coverage and price-gap screening for Batch B."""
from __future__ import annotations

import sqlite3

DB = "D:/Swing Trading/data/swing_trading.db"
SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

tables = [r["name"] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%corporate%'")]
print("corporate action tables:", tables)
for t in tables:
    print(f"  {t} rows:", conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])

print("\nLargest single-session close-to-close moves per Batch B symbol:")
for sym in SYMBOLS:
    rows = list(conn.execute(
        "SELECT d.trading_date, d.close FROM daily_ohlcv d JOIN stock_master s "
        "ON s.stock_id = d.stock_id WHERE s.nse_symbol = ? ORDER BY d.trading_date", (sym,)))
    worst = None
    for prev, cur in zip(rows, rows[1:]):
        if prev["close"] and float(prev["close"]) > 0:
            pct = (float(cur["close"]) - float(prev["close"])) / float(prev["close"]) * 100
            if worst is None or abs(pct) > abs(worst[1]):
                worst = (str(cur["trading_date"])[:10], pct, float(prev["close"]), float(cur["close"]))
    flag = "  <-- possible unadjusted corporate action" if worst and abs(worst[1]) >= 20 else ""
    print(f"  {sym:<12} max move {worst[1]:+7.2f}% on {worst[0]} "
          f"({worst[2]} -> {worst[3]}){flag}")
conn.close()
