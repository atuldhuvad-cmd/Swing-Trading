"""Prove Batch A confirm + idempotency against a database COPY, not production."""
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(r"D:\Swing Trading")
sys.path.insert(0, str(ROOT / "backend"))
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.services.ohlcv_service import OhlcvService
from app.schemas.ohlcv import OhlcvConfirmRequest

PROD = ROOT / "data" / "swing_trading.db"
COPY = ROOT / "data" / "swing_trading_batch_a_import_proof_copy.db"
FILE = ROOT / "manual_inputs" / "nse" / "Nifty50" / "13-08-2025-TO-13-08-2026-ADANIENT-ALL-N.csv"


def main():
    shutil.copy2(PROD, COPY)
    engine = create_engine(f"sqlite:///{COPY}")
    Session = sessionmaker(bind=engine)
    db = Session()
    content = FILE.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    req = OhlcvConfirmRequest(file_sha256=sha, original_filename=FILE.name, source_name="NSE")
    r1 = OhlcvService.confirm_import(db, req, content)
    n1 = db.execute(text("SELECT COUNT(*) FROM daily_ohlcv")).scalar()
    r2 = OhlcvService.confirm_import(db, req, content)
    n2 = db.execute(text("SELECT COUNT(*) FROM daily_ohlcv")).scalar()
    integrity = db.execute(text("PRAGMA integrity_check")).scalar()
    fk = list(db.execute(text("PRAGMA foreign_key_check")))
    prod_n = create_engine(f"sqlite:///{PROD}").connect().execute(text("SELECT COUNT(*) FROM daily_ohlcv")).scalar()
    print("first", r1)
    print("second", r2)
    print("copy_rows", n1, n2)
    print("integrity", integrity, "fk", fk)
    print("production_ohlcv_untouched", prod_n)
    db.close()


if __name__ == "__main__":
    main()
