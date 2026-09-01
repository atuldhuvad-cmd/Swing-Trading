"""Select NSE-filed audited annual FY2025-26 result PDFs for Batch B from announcement hits."""
from __future__ import annotations

import json
import re
from pathlib import Path

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
SYMBOLS = ["CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
           "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO"]

YEAR = re.compile(
    r"(year ended|year ended on|financial year|audited financial results).{0,80}"
    r"(31st March,? 2026|31 March,? 2026|March 31,? 2026|Mar 31,? 2026|31-03-2026|31\.03\.2026)"
    r"|period ended Mar(?:ch)? 31,? 2026"
    r"|quarter and year ended.{0,40}2026",
    re.I,
)
QUARTER_ONLY = re.compile(r"quarter ended.{0,40}(June|Sep|Dec|Jun|Sept)", re.I)


def rank(c):
    d = (c["desc"] or "").lower()
    t = (c["attchmntText"] or "").lower()
    score = 0
    if "outcome of board meeting" in d:
        score += 50
    if "financial result" in d or "financial results" in t:
        score += 20
    if "integrated filing" in d or "integrated filing" in t:
        score += 25
    if "press release" in d:
        score -= 10
    if "media release" in t:
        score -= 5
    if "audited" in t:
        score += 10
    if "consolidated" in t:
        score += 5
    return -score


def main() -> None:
    chosen = {}
    for sym in SYMBOLS:
        hits = json.loads((OUT / f"{sym}_announcement_hits.json").read_text(encoding="utf-8"))
        candidates = []
        for item in hits:
            text = " ".join(str(item.get(k) or "") for k in ("desc", "attchmntText", "attchmntFile"))
            if not YEAR.search(text):
                continue
            if QUARTER_ONLY.search(text) and "year ended" not in text.lower():
                continue
            candidates.append({
                "an_dt": item.get("an_dt"),
                "desc": item.get("desc"),
                "attchmntText": (item.get("attchmntText") or "")[:300],
                "attchmntFile": item.get("attchmntFile"),
                "fileSize": item.get("fileSize"),
            })
        candidates.sort(key=rank)
        chosen[sym] = {"count": len(candidates), "candidates": candidates[:10]}
        print("=" * 100)
        print(sym, "candidates:", len(candidates))
        for c in candidates[:5]:
            print("  ", c["an_dt"], "|", c["desc"], "|", c["attchmntText"][:110])
            print("     ", c["attchmntFile"])
    (OUT / "_batch_b_fy26_annual_candidates.json").write_text(
        json.dumps(chosen, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
