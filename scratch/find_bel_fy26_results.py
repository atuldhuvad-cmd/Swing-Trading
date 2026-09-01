"""Find BEL FY2025-26 audited result PDFs from NSE announcements and likely IR URLs."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import requests

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

IR_CANDIDATES = [
    "https://bel-india.in/wp-content/uploads/2026/05/BEL-2025-26-Q4-Financial-Results.pdf",
    "https://bel-india.in/wp-content/uploads/2026/05/BEL-Financial-Results-2025-26.pdf",
    "https://bel-india.in/wp-content/uploads/2026/05/Audited-Financial-Results-31-03-2026.pdf",
    "https://bel-india.in/wp-content/uploads/2026/05/BEL-Q4-FY26-Financial-Results.pdf",
    "https://www.bel-india.in/wp-content/uploads/2026/05/BEL-2025-26-Q4-Financial-Results.pdf",
    "https://bel-india.in/investors/financial-results/",
]


def main() -> None:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com/", timeout=30)
    r = s.get(
        f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={quote('BEL')}",
        timeout=60,
    )
    items = r.json() if r.status_code == 200 else []
    if isinstance(items, dict):
        items = items.get("data") or []
    may = []
    for it in items:
        if not isinstance(it, dict):
            continue
        dt = str(it.get("an_dt") or "") + " " + str(it.get("sort_date") or "")
        text = " ".join(str(it.get(k) or "") for k in ("desc", "attchmntText", "attchmntFile"))
        if "2026" not in dt and "2026" not in text:
            continue
        if any(k in text.lower() for k in ("financial result", "board meeting", "annual report", "integrated", "xbrl")):
            may.append(
                {
                    "an_dt": it.get("an_dt"),
                    "desc": it.get("desc"),
                    "attchmntText": it.get("attchmntText"),
                    "attchmntFile": it.get("attchmntFile"),
                    "fileSize": it.get("fileSize"),
                }
            )
    (OUT / "BEL_result_candidates.json").write_text(json.dumps(may, indent=2), encoding="utf-8")
    print("nse_candidates", len(may))
    for row in may[:25]:
        print(row["an_dt"], row["desc"], row.get("fileSize"))
        print(" ", row.get("attchmntFile"))

    s2 = requests.Session()
    s2.headers.update(
        {
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "application/pdf,*/*",
        }
    )
    ir = []
    for url in IR_CANDIDATES:
        try:
            resp = s2.get(url, timeout=30, allow_redirects=True)
            ir.append(
                {
                    "url": url,
                    "final": str(resp.url),
                    "status": resp.status_code,
                    "ctype": resp.headers.get("Content-Type"),
                    "bytes": len(resp.content),
                    "magic": resp.content[:8].decode("latin1", errors="replace"),
                }
            )
            print("IR", resp.status_code, len(resp.content), resp.headers.get("Content-Type"), url)
            if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                dest = OUT / "pdfs" / "BEL_IR_FY2025-26.pdf"
                dest.write_bytes(resp.content)
                print("saved", dest)
        except Exception as e:
            ir.append({"url": url, "error": str(e)})
            print("IR ERR", url, e)
    (OUT / "BEL_ir_probe.json").write_text(json.dumps(ir, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
