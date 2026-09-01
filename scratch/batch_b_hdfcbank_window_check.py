"""Read-only check: does unadjusted pre-bonus HDFCBANK data fall inside any indicator window?"""
from __future__ import annotations

import sqlite3

conn = sqlite3.connect("file:D:/Swing Trading/data/swing_trading.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
rows = list(conn.execute(
    "SELECT d.trading_date, d.close FROM daily_ohlcv d JOIN stock_master s "
    "ON s.stock_id = d.stock_id WHERE s.nse_symbol = 'HDFCBANK' ORDER BY d.trading_date"))
conn.close()

total = len(rows)
print("total sessions:", total)
event_idx = next(i for i, r in enumerate(rows) if str(r["trading_date"])[:10] == "2025-08-26")
print(f"bonus-adjusted price step at index {event_idx} ({str(rows[event_idx]['trading_date'])[:10]})")
print(f"pre-step sessions (indices 0..{event_idx - 1}): {event_idx}")

for window in (20, 50, 200):
    start = total - window
    contaminated = start < event_idx
    print(f"  SMA{window:<3} window covers indices {start}..{total - 1} "
          f"starting {str(rows[start]['trading_date'])[:10]}  "
          f"contains pre-step data: {contaminated}")
