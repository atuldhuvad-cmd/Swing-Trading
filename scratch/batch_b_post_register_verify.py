"""Post-registration integrity and metadata verification (read-only)."""
from __future__ import annotations

import hashlib
import pathlib
import sqlite3

DB = pathlib.Path(r"D:\Swing Trading\data\swing_trading.db")

print("POST_CHANGE_DB_SHA256", hashlib.sha256(DB.read_bytes()).hexdigest())
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
print("INTEGRITY", conn.execute("PRAGMA integrity_check").fetchone()[0])
print("FK_VIOLATIONS", len(conn.execute("PRAGMA foreign_key_check").fetchall()))

for table in ("stock_master", "daily_ohlcv", "candidate_evaluation_run",
              "candidate_criterion_result", "risk_reward_result",
              "fundamental_snapshot", "broker_recommendation"):
    print(f"{table:<28}", conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

print("SYNTHETIC_OHLCV", conn.execute(
    "SELECT COUNT(*) FROM daily_ohlcv "
    "WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
).fetchone()[0])
print("DUPLICATE_SYMBOLS", conn.execute(
    "SELECT nse_symbol, COUNT(*) c FROM stock_master GROUP BY nse_symbol HAVING c > 1"
).fetchall() or "NONE")
print("DUPLICATE_ISINS", conn.execute(
    "SELECT isin, COUNT(*) c FROM stock_master WHERE isin IS NOT NULL GROUP BY isin HAVING c > 1"
).fetchall() or "NONE")
print("INVALID_REQUIRED_FIELDS", conn.execute(
    "SELECT COUNT(*) FROM stock_master WHERE nse_symbol IS NULL OR TRIM(nse_symbol) = '' "
    "OR company_name IS NULL OR TRIM(company_name) = '' OR listing_status IS NULL"
).fetchone()[0])
print("NON_CANONICAL_SYMBOLS", conn.execute(
    "SELECT COUNT(*) FROM stock_master WHERE nse_symbol != UPPER(TRIM(nse_symbol))"
).fetchone()[0])
print("NON_ACTIVE", conn.execute(
    "SELECT nse_symbol, listing_status FROM stock_master WHERE listing_status != 'ACTIVE'"
).fetchall() or "NONE")
print("OHLCV_ROWS_FOR_NEW_STOCKS", conn.execute(
    "SELECT COUNT(*) FROM daily_ohlcv WHERE stock_id >= 19"
).fetchone()[0])
conn.close()
