"""Record production counts before UI validation. Read-only."""
import sqlite3
from pathlib import Path

DB = Path(r"D:\Swing Trading\data\swing_trading.db")
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
print("ohlcv", c.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0])
print(
    "synthetic",
    c.execute(
        "SELECT COUNT(*) FROM daily_ohlcv WHERE open=100 AND high=105 AND low=95 AND close=102 AND volume=1000"
    ).fetchone()[0],
)
print("snaps", c.execute("SELECT COUNT(*) FROM fundamental_snapshot").fetchone()[0])
print("runs", c.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0])
print("criteria", c.execute("SELECT COUNT(*) FROM candidate_criterion_result").fetchone()[0])
print("rr", c.execute("SELECT COUNT(*) FROM risk_reward_result").fetchone()[0])
print("broker", c.execute("SELECT COUNT(*) FROM broker_recommendation").fetchone()[0])
print("integrity", c.execute("PRAGMA integrity_check").fetchone()[0])
print("fk", c.execute("PRAGMA foreign_key_check").fetchall())
print(
    "batch_b_ohlcv",
    c.execute(
        """
        SELECT s.nse_symbol, COUNT(*), MIN(d.trading_date), MAX(d.trading_date)
        FROM daily_ohlcv d JOIN stock_master s ON s.stock_id=d.stock_id
        WHERE s.nse_symbol IN ('CIPLA','COALINDIA','DRREDDY','EICHERMOT','ETERNAL','GRASIM','HCLTECH','HDFCBANK','HDFCLIFE','HINDALCO')
          AND d.series='EQ'
        GROUP BY s.nse_symbol ORDER BY 1
        """
    ).fetchall(),
)
print(
    "latest_evals",
    c.execute(
        """
        SELECT s.nse_symbol, MAX(e.evaluation_id), 
               (SELECT classification FROM candidate_evaluation_run x WHERE x.evaluation_id=MAX(e.evaluation_id))
        FROM stock_master s
        JOIN candidate_evaluation_run e ON e.stock_id=s.stock_id
        WHERE s.nse_symbol IN ('CIPLA','COALINDIA','DRREDDY','EICHERMOT','ETERNAL','GRASIM','HCLTECH','HDFCBANK','HDFCLIFE','HINDALCO')
        GROUP BY s.nse_symbol ORDER BY 1
        """
    ).fetchall(),
)
c.close()
