"""Non-persistent Batch A preview using the application parser against a DB copy."""
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services.ohlcv_service import OhlcvService

SYMBOLS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL",
]
NIFTY = ROOT / "manual_inputs" / "nse" / "Nifty50"
COPY = ROOT / "data" / "swing_trading_batch_a_preview_copy.db"
PROD = ROOT / "data" / "swing_trading.db"


def pick_file(symbol: str) -> Path:
    matches = [
        p for p in NIFTY.glob("*.csv")
        if f"-{symbol}-ALL-N" in p.name and "Quote-SLB" not in p.name
    ]
    if not matches:
        raise FileNotFoundError(symbol)
    # Prefer the longest date range / newest filename
    return sorted(matches, key=lambda p: p.name)[-1]


def main():
    shutil.copy2(PROD, COPY)
    engine = create_engine(f"sqlite:///{COPY}")
    Session = sessionmaker(bind=engine)
    db = Session()
    files = [pick_file(s) for s in SYMBOLS]
    totals = defaultdict(int)
    per_symbol = {}
    try:
        for path in files:
            content = path.read_bytes()
            preview = OhlcvService.parse_historical_file(db, content, path.name)
            totals["files"] += 1
            totals["physical"] += preview.rows_received
            totals["eq"] += preview.rows_accepted + preview.rows_rejected + preview.rows_unmapped + preview.rows_duplicates + preview.rows_conflicts
            totals["ignored"] += preview.rows_ignored
            totals["accepted"] += preview.rows_accepted
            totals["invalid"] += preview.rows_rejected
            totals["unmapped"] += preview.rows_unmapped
            totals["duplicates"] += preview.rows_duplicates
            totals["conflicts"] += preview.rows_conflicts
            by = defaultdict(int)
            for row in preview.preview_rows:
                if row.status == "ACCEPTED":
                    by[row.symbol] += 1
            per_symbol[path.name] = {
                "received": preview.rows_received,
                "accepted": preview.rows_accepted,
                "ignored": preview.rows_ignored,
                "rejected": preview.rows_rejected,
                "unmapped": preview.rows_unmapped,
                "duplicates": preview.rows_duplicates,
                "conflicts": preview.rows_conflicts,
                "accepted_by_symbol": dict(by),
                "sha": preview.file_sha256,
            }
            print(path.name, per_symbol[path.name])
        ge200 = sum(1 for v in per_symbol.values() for n in v["accepted_by_symbol"].values() if n >= 200)
        print("FILES", totals["files"])
        print("PHYSICAL", totals["physical"])
        print("EQ", totals["eq"])
        print("NON_EQ", totals["ignored"])
        print("ACCEPTED", totals["accepted"])
        print("INVALID_EQ", totals["invalid"])
        print("UNMAPPED", totals["unmapped"])
        print("DUPLICATES", totals["duplicates"])
        print("CONFLICTS", totals["conflicts"])
        print("STOCKS_GE200", ge200)
        print("SMA200_READY", ge200)
        # confirm preview did not persist
        from sqlalchemy import text
        n = db.execute(text("SELECT COUNT(*) FROM daily_ohlcv")).scalar()
        print("COPY_OHLCV_ROWS_UNCHANGED", n)
    finally:
        db.close()


if __name__ == "__main__":
    main()
