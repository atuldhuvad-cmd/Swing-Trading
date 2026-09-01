"""Extract BEL FY26 Q4 results PDF text and find consolidated Revenue from operations."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

PDF = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\pdfs\BEL_2025-26-Q4-Financial-Results.pdf")
OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\BEL_IR_Q4_FY26_text.txt")

reader = PdfReader(str(PDF))
parts = []
for i, page in enumerate(reader.pages, 1):
    t = page.extract_text() or ""
    parts.append(f"\n\n----- PAGE {i} -----\n{t}")
text = "".join(parts)
OUT.write_text(text, encoding="utf-8", errors="replace")
print("pages", len(reader.pages), "chars", len(text))
for i, line in enumerate(text.splitlines(), 1):
    l = line.lower()
    if "revenue from" in l or "consolidated" in l and "result" in l or "in lakh" in l or "in crore" in l:
        print(f"L{i}: {line[:220]}")
