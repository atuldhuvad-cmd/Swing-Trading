"""Select NSE-filed audited annual FY2025-26 result PDFs from announcement hits."""
from __future__ import annotations

import json
import re
from pathlib import Path

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
SYMBOLS = [
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
]

YEAR = re.compile(
    r"(year ended|year ended on|financial year|audited financial results).{0,80}"
    r"(31st March,? 2026|31 March,? 2026|March 31,? 2026|Mar 31,? 2026|31-03-2026|31\.03\.2026)"
    r"|period ended Mar(?:ch)? 31,? 2026",
    re.I,
)
QUARTER_ONLY = re.compile(r"quarter ended.{0,40}(June|Sep|Dec|Jun|Sept)", re.I)


def main() -> None:
    chosen = {}
    for sym in SYMBOLS:
        hits = json.loads((OUT / f"{sym}_announcement_hits.json").read_text(encoding="utf-8"))
        candidates = []
        for item in hits:
            text = " ".join(
                str(item.get(k) or "")
                for k in ("desc", "attchmntText", "attchmntFile")
            )
            if not YEAR.search(text):
                continue
            if QUARTER_ONLY.search(text) and "year ended" not in text.lower():
                continue
            candidates.append(
                {
                    "an_dt": item.get("an_dt"),
                    "desc": item.get("desc"),
                    "attchmntText": item.get("attchmntText"),
                    "attchmntFile": item.get("attchmntFile"),
                    "fileSize": item.get("fileSize"),
                }
            )
        # Prefer Outcome of Board Meeting / Financial Results over Press Release
        def rank(c):
            d = (c["desc"] or "").lower()
            t = (c["attchmntText"] or "").lower()
            score = 0
            if "outcome of board meeting" in d:
                score += 50
            if "financial result" in d or "financial results" in t:
                score += 20
            if "press release" in d:
                score -= 10
            if "media release" in t:
                score -= 5
            if "audited" in t:
                score += 10
            if "consolidated" in t:
                score += 5
            return -score

        candidates.sort(key=rank)
        chosen[sym] = {"count": len(candidates), "candidates": candidates[:8]}
        print(sym, len(candidates))
        if candidates:
            print(" ", candidates[0]["desc"], candidates[0]["attchmntFile"])
    (OUT / "_fy26_annual_candidates.json").write_text(
        json.dumps(chosen, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
