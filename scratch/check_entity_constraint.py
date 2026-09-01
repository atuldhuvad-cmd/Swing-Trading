"""Read-only check of the fundamental_snapshot DDL and alembic revision in production."""
from __future__ import annotations

import sqlite3

conn = sqlite3.connect("file:D:/Swing Trading/data/swing_trading.db?mode=ro", uri=True)
row = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='fundamental_snapshot'").fetchone()
print("=== fundamental_snapshot DDL ===")
print(row[0] if row else "TABLE MISSING")
try:
    print("\nalembic_version:", conn.execute("SELECT * FROM alembic_version").fetchall())
except sqlite3.OperationalError as e:
    print("\nalembic_version:", e)
print("\nsnapshot rows:", conn.execute("SELECT COUNT(*) FROM fundamental_snapshot").fetchone()[0])
print("distinct entity_type:", conn.execute(
    "SELECT entity_type, COUNT(*) FROM fundamental_snapshot GROUP BY entity_type").fetchall())
conn.close()
