"""List HDFCBANK FY26 result-related NSE announcement attachments."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
p = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\HDFCBANK_announcement_hits.json")
hits = json.loads(p.read_text(encoding="utf-8"))
for item in hits:
    dt = str(item.get("an_dt") or "")
    desc = str(item.get("desc") or "")
    txt = str(item.get("attchmntText") or "")
    blob = (desc + " " + txt).lower()
    if "2026" not in dt:
        continue
    if any(k in blob for k in ("financial result", "outcome", "audited", "integrated filing", "xbrl")):
        print("-" * 90)
        print(dt, "|", desc)
        print(" ", txt[:250])
        print(" ", item.get("attchmntFile"))
