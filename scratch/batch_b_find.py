"""Search extracted Batch B PDF text for a pattern and print page-anchored context lines."""
from __future__ import annotations

import re
import sys
from pathlib import Path

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    sym = sys.argv[1]
    pattern = sys.argv[2]
    ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    raw = (OUT / f"{sym}_batchb_pdf_text.txt").read_text(encoding="utf-8", errors="replace")
    lines = raw.replace("\x00", "").splitlines()
    pat = re.compile(pattern, re.I)
    page = "?"
    hits = 0
    for i, line in enumerate(lines):
        if line.startswith("----- PAGE "):
            page = line.strip()
        if pat.search(line):
            hits += 1
            print(f"--- [{page}] line {i}")
            for j in range(max(0, i - ctx), min(len(lines), i + ctx + 1)):
                print(f"{j:6d}| {lines[j]}")
    print(f"[{sym}] pattern={pattern!r} hits={hits} total_lines={len(lines)}")


if __name__ == "__main__":
    main()
