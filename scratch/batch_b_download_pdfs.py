"""Download selected NSE-filed FY2025-26 annual result PDFs for Batch B."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
PDF_DIR = OUT / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "CIPLA": "https://nsearchives.nseindia.com/corporate/CIPLA_13052026123600_SignedFinancialResults13052026Signed.pdf",
    "COALINDIA": "https://nsearchives.nseindia.com/corporate/COALINDIA_27042026202823_result_final.pdf",
    "DRREDDY": "https://nsearchives.nseindia.com/corporate/DRREDDY_12052026163727_SEintimation_Outcome_of_BM_12052026_signed.pdf",
    "EICHERMOT": "https://nsearchives.nseindia.com/corporate/EICHERMOT_22052026164926_EMLOutcomeofBoardMeetingMay222026Signed.pdf",
    "ETERNAL": "https://nsearchives.nseindia.com/corporate/ZOMATO_28042026150911_Outcomesigned.pdf",
    "GRASIM": "https://nsearchives.nseindia.com/corporate/GRASIM_20052026143701_Seintimationfinal.pdf",
    "HCLTECH": "https://nsearchives.nseindia.com/corporate/HCLTECH_21042026175820_FinancialResults.pdf",
    "HDFCBANK": "https://nsearchives.nseindia.com/corporate/HDFCBANK_18042026144226_SEResultOutcome18042026.pdf",
    "HDFCLIFE": "https://nsearchives.nseindia.com/corporate/PRASAD_16042026163334_Board.pdf",
    "HINDALCO": "https://nsearchives.nseindia.com/corporate/HINDALCOIND_22052026171757_BM_Outcome_2205_final_signed.pdf",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
    "Referer": "https://www.nseindia.com/",
}


def warm(s: requests.Session) -> None:
    for _ in range(5):
        try:
            s.get("https://www.nseindia.com/", timeout=45)
            return
        except Exception as e:
            print("warm retry:", str(e)[:100])
            time.sleep(5)


def fetch(s: requests.Session, url: str, attempts: int = 5):
    last = None
    for i in range(attempts):
        try:
            return s.get(url, timeout=240)
        except Exception as e:
            last = e
            print("  retry", i + 1, str(e)[:100])
            time.sleep(5 * (i + 1))
            warm(s)
    raise last


def main() -> None:
    s = requests.Session()
    s.headers.update(HEADERS)
    warm(s)
    manifest = {}
    for sym, url in FILES.items():
        dest = PDF_DIR / f"{sym}_FY2025-26_annual.pdf"
        r = fetch(s, url)
        dest.write_bytes(r.content)
        manifest[sym] = {
            "url": url,
            "status": r.status_code,
            "bytes": len(r.content),
            "content_type": r.headers.get("Content-Type"),
            "path": str(dest),
            "pdf_magic": r.content[:5].decode("latin1", errors="replace"),
            "sha256": hashlib.sha256(r.content).hexdigest(),
        }
        print(sym, r.status_code, len(r.content), r.headers.get("Content-Type"), dest.name)
    (OUT / "_batch_b_pdf_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
