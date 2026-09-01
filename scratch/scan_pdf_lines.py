"""Locate canonical P&L lines in extracted FY26 PDF text."""
from __future__ import annotations

import re
from pathlib import Path

DIR = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
NEEDLES = [
    "Revenue from operations",
    "Revenue from Operations",
    "Total Income",
    "Total income",
    "Consolidated",
    "Standalone",
    "in Crore",
    "in Million",
    "in crore",
]


def main() -> None:
    for p in sorted(DIR.glob("*_pdf_text.txt")):
        text = p.read_text(encoding="utf-8", errors="replace")
        print("====", p.name, "chars", len(text))
        for n in NEEDLES:
            c = text.lower().count(n.lower())
            if c:
                print(f"  {n}: {c}")
        # print lines containing revenue/total income
        hits = []
        for i, line in enumerate(text.splitlines(), 1):
            l = line.lower()
            if "revenue from" in l or "total income" in l:
                hits.append((i, line.strip()[:200]))
        for i, line in hits[:12]:
            print(f"  L{i}: {line}")
        print("  ... total matching lines", len(hits))


if __name__ == "__main__":
    main()
