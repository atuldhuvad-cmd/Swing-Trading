from pathlib import Path
import re
p = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\BEL_pdf_text.txt")
s = re.sub(r"\s+", " ", p.read_text(encoding="utf-8", errors="replace"))
out = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings\_bel_compact.txt")
out.write_text(s, encoding="utf-8")
for needle in ["9 , 56 , 207", "27 , 479", "consolidated", "standalone", "Lakhs"]:
    print(needle, s.lower().count(needle.lower()))
idx = s.lower().find("9 , 56 , 207")
print("context956", s[max(0, idx-400): idx+400] if idx>=0 else None)
idx = s.lower().find("27 , 479")
print("context27479", s[max(0, idx-300): idx+300] if idx>=0 else None)
