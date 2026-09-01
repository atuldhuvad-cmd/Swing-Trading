"""Final read-only forensic verification of the Batch B OHLCV import."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

DB = Path(r"D:\Swing Trading\data\swing_trading.db")
SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]
EXPECTED_SHA = {
    "CIPLA": "a0352bff049b6bc452944c2b0ac78928aab8c5a66937d793d824b4f8a5593b5c",
    "COALINDIA": "85b8a1150d1740074e5464f680c642d46a8d19478864874cd906e8feb9d3e4dc",
    "DRREDDY": "8608cb8ab0671951f144b8eb99ce0de0be565c0b8dc1bb895c07edba59194720",
    "EICHERMOT": "d7da7cccd5191f43544c75a434bee700d961aa6de27cf57c1d69b9fec49238a8",
    "ETERNAL": "fc3aed490c2a127f82ba14b3168fc5292be1d692fc6f830e6572eb7245cabc8f",
    "GRASIM": "c457abb57f4a855a782778948a21063e30dea0a42c7d344fd38631ecd3838269",
    "HCLTECH": "d01222ab542dc511f5dcbe65530b68ffaa599b72397c2f4cb8d49e2ea96b3e95",
    "HDFCBANK": "b226a83c697306e81e16b3374d47bb2ab311ad998558bd0990fb5a5f96c43efd",
    "HDFCLIFE": "0f5f11d3a546551cb37dae1d49749e62563d45f1a997049909582940f7a29e9a",
    "HINDALCO": "310d81bc101f7d1c7aa249f9cc7a179a72769c899a01cbde0ccc234f7600e60d",
}

print("DB_SHA256", hashlib.sha256(DB.read_bytes()).hexdigest())
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

print("\n=== PER-SYMBOL PROVENANCE AND QUALITY ===")
for sym in SYMBOLS:
    row = conn.execute(
        "SELECT s.stock_id, COUNT(*) rows, COUNT(DISTINCT d.trading_date) sessions, "
        "MIN(d.trading_date) lo, MAX(d.trading_date) hi, "
        "SUM(CASE WHEN d.series != 'EQ' THEN 1 ELSE 0 END) non_eq, "
        "SUM(CASE WHEN d.volume < 0 THEN 1 ELSE 0 END) bad_vol, "
        "SUM(CASE WHEN NOT (d.low <= d.open AND d.open <= d.high AND d.low <= d.close "
        "AND d.close <= d.high) THEN 1 ELSE 0 END) bad_ohlc, "
        "SUM(CASE WHEN d.source_name IS NULL OR d.import_batch_id IS NULL THEN 1 ELSE 0 END) no_prov "
        "FROM stock_master s JOIN daily_ohlcv d ON d.stock_id = s.stock_id "
        "WHERE s.nse_symbol = ? GROUP BY s.stock_id", (sym,)).fetchone()
    batches = conn.execute(
        "SELECT DISTINCT b.import_batch_id, b.original_filename, b.file_sha256, "
        "b.source_name, b.source_reference FROM daily_ohlcv d "
        "JOIN data_import_batch b ON b.import_batch_id = d.import_batch_id "
        "JOIN stock_master s ON s.stock_id = d.stock_id WHERE s.nse_symbol = ?", (sym,)).fetchall()
    sha_ok = all(b["file_sha256"] == EXPECTED_SHA[sym] for b in batches)
    print(f"\n{sym}")
    print(f"  stock_id={row['stock_id']}  rows={row['rows']}  sessions={row['sessions']}  "
          f"{str(row['lo'])[:10]}..{str(row['hi'])[:10]}")
    print(f"  non_eq={row['non_eq']}  bad_ohlc={row['bad_ohlc']}  bad_volume={row['bad_vol']}  "
          f"missing_provenance={row['no_prov']}")
    print(f"  SMA200_ready={row['sessions'] >= 200}  file_sha_traceable={sha_ok}")
    for b in batches:
        print(f"  batch {b['import_batch_id']}: {b['original_filename']} "
              f"source={b['source_name']} ref={b['source_reference']}")
        print(f"    sha256={b['file_sha256']}")

print("\n=== GLOBAL ===")
q = conn.execute
print("total_ohlcv          ", q("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0])
print("stock_master         ", q("SELECT COUNT(*) FROM stock_master").fetchone()[0])
print("duplicate_symbols    ", q("SELECT nse_symbol, COUNT(*) c FROM stock_master "
                                 "GROUP BY nse_symbol HAVING c>1").fetchall() or "NONE")
print("synthetic_ohlcv      ", q("SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 "
                                 "AND low=95 AND close=102 AND volume=1000").fetchone()[0])
print("duplicate_ohlcv_keys ", q("SELECT COUNT(*) FROM (SELECT stock_id, trading_date, series, "
                                 "COUNT(*) c FROM daily_ohlcv GROUP BY 1,2,3 HAVING c>1)").fetchone()[0])
print("non_eq_rows          ", q("SELECT COUNT(*) FROM daily_ohlcv WHERE series != 'EQ'").fetchone()[0])
print("rows_missing_prov    ", q("SELECT COUNT(*) FROM daily_ohlcv WHERE source_name IS NULL "
                                 "OR source_name='' OR import_batch_id IS NULL").fetchone()[0])
print("stocks_ge_200        ", q("SELECT COUNT(*) FROM (SELECT stock_id FROM daily_ohlcv "
                                 "GROUP BY stock_id HAVING COUNT(DISTINCT trading_date) >= 200)").fetchone()[0])
print("import_batches       ", q("SELECT COUNT(*) FROM data_import_batch").fetchone()[0])
print("integrity_check      ", q("PRAGMA integrity_check").fetchone()[0])
print("foreign_key_check    ", len(q("PRAGMA foreign_key_check").fetchall()))
print("\nrows per stock:")
for r in q("SELECT s.nse_symbol, COUNT(*) n FROM daily_ohlcv d "
           "JOIN stock_master s ON s.stock_id = d.stock_id "
           "GROUP BY s.nse_symbol ORDER BY s.nse_symbol"):
    print(f"  {r['nse_symbol']:<12} {r['n']}")
conn.close()
