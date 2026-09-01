"""Print context around canonical revenue lines in Batch B result PDFs text."""
from __future__ import annotations

import re
import sys
from pathlib import Path

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")


def main() -> None:
    sym = sys.argv[1]
    pattern = sys.argv[2] if len(sys.argv) > 2 else r"Revenue from operations"
    before = int(sys.argv[3]) if len(sys.argv) > 3 else 700
    after = int(sys.argv[4]) if len(sys.argv) > 4 else 700
    text = (OUT / f"{sym}_batchb_pdf_text.txt").read_text(encoding="utf-8", errors="replace")
    pat = re.compile(pattern, re.I)
    for m in pat.finditer(text):
        page = text.rfind("----- PAGE ", 0, m.start())
        page_no = text[page:page + 25].strip() if page >= 0 else "?"
        print("=" * 110)
        print(f"[{page_no}] offset {m.start()}")
        print(text[max(0, m.start() - before): m.end() + after])


if __name__ == "__main__":
    main()
