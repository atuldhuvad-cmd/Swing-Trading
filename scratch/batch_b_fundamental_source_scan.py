"""Read-only scan of Batch A source_reference rows and locally available primary documents."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]

conn = sqlite3.connect("file:D:/Swing Trading/data/swing_trading.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
print("=== source_reference columns ===")
print([r["name"] for r in conn.execute("PRAGMA table_info(source_reference)")])
print("\n=== source_reference rows used by fundamental snapshots ===")
for r in conn.execute(
    "SELECT sr.*, s.nse_symbol FROM source_reference sr "
    "JOIN fundamental_snapshot f ON f.source_reference_id = sr.source_reference_id "
    "JOIN stock_master s ON s.stock_id = f.stock_id ORDER BY sr.source_reference_id"
):
    d = dict(r)
    print(f"\n  {d.pop('nse_symbol')}")
    for k, v in d.items():
        print(f"    {k}: {v}")
conn.close()

print("\n=== LOCAL DOCUMENT INVENTORY (manual_inputs) ===")
roots = [ROOT / "manual_inputs"]
pdfs = []
for base in roots:
    if base.exists():
        pdfs = sorted(p for p in base.rglob("*.pdf"))
print(f"total PDFs under manual_inputs: {len(pdfs)}")
for p in pdfs:
    print(f"  {p.relative_to(ROOT)}  ({p.stat().st_size} bytes)")

print("\n=== PER-SYMBOL LOCAL PRIMARY EVIDENCE MATCH ===")
for sym in SYMBOLS:
    hits = [p for p in pdfs if sym.lower().replace("-", "") in p.name.lower().replace("-", "")]
    print(f"  {sym:<12} {'FOUND: ' + ', '.join(h.name for h in hits) if hits else 'NOT PRESENT LOCALLY'}")

print("\n=== fundamentals directories ===")
for base in roots:
    for d in sorted(x for x in base.rglob("*") if x.is_dir()):
        files = [f for f in d.iterdir() if f.is_file()]
        print(f"  {d.relative_to(ROOT)}  ({len(files)} files)")
