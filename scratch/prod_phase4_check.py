import sqlite3

p = r"D:\Swing Trading\data\swing_trading.db"
c = sqlite3.connect(p)
cur = c.cursor()
print("integrity", cur.execute("PRAGMA integrity_check").fetchone()[0])
print("fk", cur.execute("PRAGMA foreign_key_check").fetchall())
print("ohlcv", cur.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0])
print(
    "synthetic",
    cur.execute(
        "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
    ).fetchone()[0],
)
print("fund_snaps", cur.execute("SELECT COUNT(*) FROM fundamental_snapshot").fetchone()[0])
print("fund_metrics", cur.execute("SELECT COUNT(*) FROM fundamental_metric").fetchone()[0])
print("evals", cur.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0])
print("latest_class")
for r in cur.execute(
    """
    SELECT classification, COUNT(*) FROM (
      SELECT stock_id, classification FROM candidate_evaluation_run e
      WHERE evaluation_id = (
        SELECT MAX(evaluation_id) FROM candidate_evaluation_run e2 WHERE e2.stock_id=e.stock_id
      )
    ) GROUP BY classification
    """
):
    print(r)
print(
    "fund_batches",
    cur.execute("SELECT COUNT(*) FROM data_import_batch WHERE import_type='FUNDAMENTAL_MANUAL'").fetchone()[0],
)
print(
    "source_manual",
    cur.execute("SELECT COUNT(*) FROM source_type_master WHERE type_name='MANUAL_FUNDAMENTAL'").fetchone()[0],
)
