"""Locate ETERNAL (formerly Zomato) FY2025-26 audited annual results filing on NSE."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
data = json.loads((OUT / "ETERNAL_announcements.json").read_text(encoding="utf-8"))
items = data if isinstance(data, list) else data.get("data", [])
print("total announcements:", len(items))

for it in items:
    if not isinstance(it, dict):
        continue
    dt = str(it.get("an_dt") or "")
    desc = str(it.get("desc") or "")
    txt = str(it.get("attchmntText") or "")
    blob = (desc + " " + txt).lower()
    if ("2026" in dt) and ("apr" in dt.lower() or "may" in dt.lower() or "jun" in dt.lower()):
        if ("outcome" in blob or "financial result" in blob or "integrated filing" in blob
                or "audited" in blob):
            print("-" * 90)
            print(dt, "|", desc)
            print("  ", txt[:220])
            print("  ", it.get("attchmntFile"))
