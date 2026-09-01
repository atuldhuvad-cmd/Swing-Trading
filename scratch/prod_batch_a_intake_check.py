import sqlite3

p = r"D:\Swing Trading\data\swing_trading.db"
c = sqlite3.connect(p)
cur = c.cursor()
syms = (
    "ADANIENT",
    "ADANIPORTS",
    "APOLLOHOSP",
    "ASIANPAINT",
    "AXISBANK",
    "BAJAJ-AUTO",
    "BAJAJFINSV",
    "BAJFINANCE",
    "BEL",
    "BHARTIARTL",
)
print("stocks")
q = (
    "SELECT nse_symbol, company_name, sector, industry, isin FROM stock_master "
    "WHERE nse_symbol IN ({})".format(",".join("?" * len(syms)))
)
for r in cur.execute(q, syms):
    print(r)
print("counts")
print("ohlcv", cur.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0])
print("fund_snaps", cur.execute("SELECT COUNT(*) FROM fundamental_snapshot").fetchone()[0])
print(
    "fund_batches",
    cur.execute(
        "SELECT COUNT(*) FROM data_import_batch WHERE import_type='FUNDAMENTAL_MANUAL'"
    ).fetchone()[0],
)
print("evals", cur.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0])
print("integrity", cur.execute("PRAGMA integrity_check").fetchone()[0])
print("fk", cur.execute("PRAGMA foreign_key_check").fetchall())
print(
    "synthetic",
    cur.execute(
        "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
    ).fetchone()[0],
)
