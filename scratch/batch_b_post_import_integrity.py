import sqlite3

c = sqlite3.connect(r"D:\Swing Trading\data\swing_trading.db")
print("integrity", c.execute("PRAGMA integrity_check").fetchone()[0])
print("fk", c.execute("PRAGMA foreign_key_check").fetchall())
print("snaps", c.execute("SELECT COUNT(*) FROM fundamental_snapshot").fetchone()[0])
print(
    "batch_b",
    c.execute(
        """
        SELECT COUNT(*) FROM fundamental_snapshot fs
        JOIN stock_master s ON s.stock_id=fs.stock_id
        WHERE s.nse_symbol IN (
            'CIPLA','COALINDIA','DRREDDY','EICHERMOT','ETERNAL',
            'GRASIM','HCLTECH','HDFCBANK','HDFCLIFE','HINDALCO'
        )
        """
    ).fetchone()[0],
)
print(
    "manual_batches",
    c.execute(
        "SELECT status, COUNT(*) FROM data_import_batch WHERE import_type='FUNDAMENTAL_MANUAL' GROUP BY status"
    ).fetchall(),
)
print(
    "hdfclife",
    c.execute(
        """
        SELECT fs.entity_type, fs.source_line_item, fs.original_unit, fs.statement_scope,
               fm.metric_value, fm.status, fs.version, fs.is_superseded
        FROM fundamental_snapshot fs
        JOIN stock_master s ON s.stock_id=fs.stock_id
        JOIN fundamental_metric fm ON fm.snapshot_id=fs.snapshot_id AND fm.metric_name='revenue'
        WHERE s.nse_symbol='HDFCLIFE'
        """
    ).fetchall(),
)
