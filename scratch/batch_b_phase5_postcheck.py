"""Post-check Batch B Phase 5 re-eval without creating new runs."""
from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

DB = Path(r"D:\Swing Trading\data\swing_trading.db")
BATCH_B = {
    "CIPLA": Decimal("28162.59"),
    "COALINDIA": Decimal("168400.29"),
    "DRREDDY": Decimal("33700.2"),
    "EICHERMOT": Decimal("23407.56"),
    "ETERNAL": Decimal("54364"),
    "GRASIM": Decimal("175430.74"),
    "HCLTECH": Decimal("130144"),
    "HDFCBANK": Decimal("495462.81"),
    "HDFCLIFE": Decimal("98770.38"),
    "HINDALCO": Decimal("274944"),
}
BATCH_A = {
    "ADANIENT": Decimal("100468.61"),
    "ADANIPORTS": Decimal("38735.77"),
    "APOLLOHOSP": Decimal("25228.50"),
    "ASIANPAINT": Decimal("35583.54"),
    "AXISBANK": Decimal("162211.95"),
    "BAJAJ-AUTO": Decimal("62905.00"),
    "BAJAJFINSV": Decimal("150501.77"),
    "BAJFINANCE": Decimal("81989.50"),
    "BEL": Decimal("27610.11"),
    "BHARTIARTL": Decimal("210972.80"),
}

c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = {
    r[0]: (Decimal(str(r[1])), r[2], r[3], r[4])
    for r in c.execute(
        """
        SELECT s.nse_symbol, fm.metric_value, fm.status, fs.entity_type, fs.source_line_item
        FROM fundamental_snapshot fs
        JOIN stock_master s ON s.stock_id=fs.stock_id
        JOIN fundamental_metric fm ON fm.snapshot_id=fs.snapshot_id AND fm.metric_name='revenue'
        WHERE fs.is_superseded=0
        """
    )
}
print("snap_count", len(rows))
b_ok = all(rows[s][0] == v and rows[s][1] == "KNOWN" for s, v in BATCH_B.items())
a_ok = all(rows[s][0] == v and rows[s][1] == "KNOWN" for s, v in BATCH_A.items())
print("BATCH_B_REVENUE_OK", b_ok)
print("BATCH_A_REVENUE_OK", a_ok)
print("HDFCLIFE", rows["HDFCLIFE"])
print("runs", c.execute("SELECT COUNT(*) FROM candidate_evaluation_run").fetchone()[0])
print("new_ids", [r[0] for r in c.execute("SELECT evaluation_id FROM candidate_evaluation_run WHERE evaluation_id>=34 ORDER BY 1")])
print("per_b", c.execute(
    """
    SELECT s.nse_symbol, COUNT(*), MAX(e.evaluation_id), MAX(e.classification)
    FROM stock_master s JOIN candidate_evaluation_run e ON e.stock_id=s.stock_id
    WHERE s.nse_symbol IN ('CIPLA','COALINDIA','DRREDDY','EICHERMOT','ETERNAL','GRASIM','HCLTECH','HDFCBANK','HDFCLIFE','HINDALCO')
    GROUP BY s.nse_symbol ORDER BY 1
    """
).fetchall())
print("unknown_pass", c.execute(
    """
    SELECT s.nse_symbol, c.criterion_identifier, c.state, e.classification
    FROM candidate_criterion_result c
    JOIN candidate_evaluation_run e ON e.evaluation_id=c.evaluation_id
    JOIN stock_master s ON s.stock_id=e.stock_id
    WHERE e.evaluation_id>=34 AND (c.state='UNKNOWN' OR (c.state='PASS' AND c.reason LIKE '%UNKNOWN%'))
    """
).fetchall())
print("integrity", c.execute("PRAGMA integrity_check").fetchone()[0])
print("fk", c.execute("PRAGMA foreign_key_check").fetchall())
c.close()
