from decimal import Decimal
import sqlite3

EXPECTED = {
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
ENT = {
    "AXISBANK": "BANK",
    "BAJFINANCE": "NBFC",
}
conn = sqlite3.connect(r"D:\Swing Trading\data\swing_trading.db")
rows = conn.execute(
    """
    SELECT s.nse_symbol, fs.entity_type, fs.financial_period, fs.period_type, fs.as_of_date,
           fs.version, fs.is_superseded, fm.metric_value, fm.status, sr.publication_name, sr.url
    FROM fundamental_snapshot fs
    JOIN stock_master s ON s.stock_id=fs.stock_id
    JOIN fundamental_metric fm ON fm.snapshot_id=fs.snapshot_id AND fm.metric_name='revenue'
    JOIN source_reference sr ON sr.source_reference_id=fs.source_reference_id
    ORDER BY s.nse_symbol
    """
).fetchall()
ok = True
for r in rows:
    sym, ent, per, ptype, asof, ver, sup, val, status, pub, url = r
    exp = EXPECTED[sym]
    got = Decimal(str(val))
    want_ent = ENT.get(sym, "ORDINARY")
    checks = {
        "entity": ent == want_ent,
        "period": per == "FY2025-26",
        "ptype": ptype == "ANNUAL",
        "asof": asof == "2026-03-31",
        "ver": ver == 1,
        "sup": sup == 0,
        "status": status == "KNOWN",
        "value": got == exp,
    }
    if not all(checks.values()):
        ok = False
    print(sym, ent, per, ptype, asof, "v", ver, "sup", sup, val, status, checks)
print("ALL_OK", ok, "n", len(rows))
print("metrics_per_snap", conn.execute("SELECT snapshot_id, COUNT(*) FROM fundamental_metric GROUP BY snapshot_id").fetchall())
print("integrity", conn.execute("PRAGMA integrity_check").fetchone()[0])
print("fk", conn.execute("PRAGMA foreign_key_check").fetchall())
