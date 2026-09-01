"""Read-only inspection of existing OHLCV provenance conventions."""
from __future__ import annotations

import importlib.util
import sqlite3

print("REQUESTS_AVAILABLE", importlib.util.find_spec("requests") is not None)

conn = sqlite3.connect("file:D:/Swing Trading/data/swing_trading.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

print("\n--- daily_ohlcv columns ---")
print([r["name"] for r in conn.execute("PRAGMA table_info(daily_ohlcv)")])

print("\n--- distinct source_name / series ---")
for r in conn.execute("SELECT source_name, series, COUNT(*) n FROM daily_ohlcv GROUP BY source_name, series"):
    print(" ", dict(r))

print("\n--- rows per stock (existing) ---")
for r in conn.execute(
    "SELECT o.stock_id, s.nse_symbol, COUNT(*) n, MIN(o.trading_date) lo, MAX(o.trading_date) hi, "
    "COUNT(DISTINCT o.import_batch_id) batches "
    "FROM daily_ohlcv o JOIN stock_master s ON s.stock_id = o.stock_id "
    "GROUP BY o.stock_id, s.nse_symbol ORDER BY o.stock_id"
):
    print(" ", dict(r))

print("\n--- data_import_batch columns ---")
print([r["name"] for r in conn.execute("PRAGMA table_info(data_import_batch)")])

print("\n--- OHLCV import batches ---")
for r in conn.execute(
    "SELECT import_batch_id, import_type, source_name, source_reference, original_filename, "
    "status, rows_received, rows_accepted, rows_rejected, file_sha256 "
    "FROM data_import_batch WHERE import_type LIKE '%OHLCV%' ORDER BY import_batch_id"
):
    print(" ", dict(r))

print("\n--- import_type breakdown ---")
for r in conn.execute("SELECT import_type, COUNT(*) n FROM data_import_batch GROUP BY import_type"):
    print(" ", dict(r))

conn.close()
