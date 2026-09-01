import sqlite3
from pathlib import Path

PROD = Path(r"D:\Swing Trading\data\swing_trading.db")
c = sqlite3.connect(f"file:{PROD}?mode=ro", uri=True)
print("alembic", list(c.execute("SELECT * FROM alembic_version")))
print("\nstocks:")
for r in c.execute("SELECT stock_id, nse_symbol, company_name FROM stock_master ORDER BY stock_id"):
    print(r)
print("\nbatches:")
for r in c.execute("SELECT * FROM data_import_batch"):
    print(r)
print("\nrecs:")
for r in c.execute("SELECT recommendation_id, stock_id, broker_id, recommendation_date, original_rating, target_price, stop_loss FROM broker_recommendation"):
    print(r)
print("\nohlcv distinct values:")
print(list(c.execute("SELECT DISTINCT open, high, low, close, volume FROM daily_ohlcv")))
print("dates sample high", list(c.execute("SELECT DISTINCT trading_date FROM daily_ohlcv ORDER BY trading_date DESC LIMIT 10")))
print("metric tables", list(c.execute("SELECT name FROM sqlite_master WHERE name LIKE '%metric%' OR name LIKE '%risk%'")))
c.close()
