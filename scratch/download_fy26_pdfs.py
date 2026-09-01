"""Download selected NSE-filed FY2025-26 annual result PDFs."""
from __future__ import annotations

import json
from pathlib import Path

import requests

OUT = Path(r"D:\Swing Trading\manual_inputs\fundamentals\filings")
PDF_DIR = OUT / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "ADANIENT": "https://nsearchives.nseindia.com/corporate/ADANIENT_30042026153306_AELBMOutcome30042026.pdf",
    "ADANIPORTS": "https://nsearchives.nseindia.com/corporate/rkbhagia_30042026134205_OutcomeofBoardMeeting.pdf",
    "APOLLOHOSP": "https://nsearchives.nseindia.com/corporate/APOLLOHOSP_20052026175246_SE_outcome_Board_Meeting.pdf",
    "ASIANPAINT": "https://nsearchives.nseindia.com/corporate/ASIANPAINT_29052026140521_SEIntimationoutcomeFY26.pdf",
    "AXISBANK": "https://nsearchives.nseindia.com/corporate/AXISBANK1_25042026125818_AFRQ4FY26.pdf",
    "BAJAJ-AUTO": "https://nsearchives.nseindia.com/corporate/lkwalimbe_bajajauto_co_in_06052026182412_Outcome_of_Board_Meeting.pdf",
    "BAJAJFINSV": "https://nsearchives.nseindia.com/corporate/walimbelk_30042026141401_BFSBMOUTCOMEFINAL30APRIL2026_1.pdf",
    "BAJFINANCE": "https://nsearchives.nseindia.com/corporate/BAJFINANCE_29042026163247_BSENSEOUTCOME.pdf",
    "BEL": "https://nsearchives.nseindia.com/corporate/BEL_19052026151725_Letter_signed.pdf",
    "BHARTIARTL": "https://nsearchives.nseindia.com/corporate/BHARTIARTL_13052026163920_FR_Final.pdf",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
    "Referer": "https://www.nseindia.com/",
}


def main() -> None:
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.nseindia.com/", timeout=30)
    manifest = {}
    for sym, url in FILES.items():
        dest = PDF_DIR / f"{sym}_FY2025-26_annual.pdf"
        r = s.get(url, timeout=120)
        dest.write_bytes(r.content)
        manifest[sym] = {
            "url": url,
            "status": r.status_code,
            "bytes": len(r.content),
            "content_type": r.headers.get("Content-Type"),
            "path": str(dest),
            "pdf_magic": r.content[:5].decode("latin1", errors="replace"),
        }
        print(sym, r.status_code, len(r.content), r.headers.get("Content-Type"), dest.name)
    (OUT / "_pdf_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
