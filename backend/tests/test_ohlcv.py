import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import io
import json

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}, 
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    from app.models import StockMaster, DailyOhlcv, DataImportBatch
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    from tests.schema_helpers import stamp_head
    stamp_head(engine)
    db = TestingSessionLocal()
    db.add(StockMaster(nse_symbol="ADANIENT", company_name="Adani Ent", listing_status="ACTIVE"))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)

def test_ohlcv_preview_eq_only():
    csv_content = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","EQ","13-Aug-2026","3000","3050","2950","3020","100000"
"""
    response = client.post("/api/ohlcv/preview", files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["rows_received"] == 1
    assert data["rows_accepted"] == 1
    assert data["rows_rejected"] == 0
    assert data["rows_ignored"] == 0

def test_ohlcv_preview_mixed_eq_bl():
    csv_content = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","EQ","13-Aug-2026","3000","3050","2950","3020","100000"
"ADANIENT","BL","13-Aug-2026","3000","3050","2950","3020","50000"
"""
    response = client.post("/api/ohlcv/preview", files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["rows_received"] == 2
    assert data["rows_accepted"] == 1
    assert data["rows_rejected"] == 0
    assert data["rows_ignored"] == 1

def test_ohlcv_preview_no_eq():
    csv_content = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","BL","13-Aug-2026","3000","3050","2950","3020","50000"
"""
    response = client.post("/api/ohlcv/preview", files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")})
    assert response.status_code == 500 or response.status_code == 400
    # Expected to fail validation because no EQ rows found

def test_ohlcv_preview_malformed_eq():
    csv_content = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","EQ","13-Aug-2026","-3000","3050","2950","3020","100000"
"""
    response = client.post("/api/ohlcv/preview", files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["rows_received"] == 1
    assert data["rows_accepted"] == 0
    assert data["rows_rejected"] == 1
    assert data["rows_ignored"] == 0
    assert "Invalid negative/zero OHLCV" in data["preview_rows"][0]["message"]

def test_ohlcv_preview_mixed_valid_eq_malformed_bl():
    csv_content = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","EQ","13-Aug-2026","3000","3050","2950","3020","100000"
"ADANIENT","BL","13-Aug-2026","NOT_A_NUMBER","3050","2950","3020","50000"
"""
    response = client.post("/api/ohlcv/preview", files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["rows_received"] == 2
    assert data["rows_accepted"] == 1
    assert data["rows_rejected"] == 0
    assert data["rows_ignored"] == 1

def test_ohlcv_preview_mixed_valid_eq_malformed_eq():
    csv_content = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","EQ","13-Aug-2026","3000","3050","2950","3020","100000"
"ADANIENT","EQ","14-Aug-2026","0","3050","2950","3020","100000"
"""
    response = client.post("/api/ohlcv/preview", files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["rows_received"] == 2
    assert data["rows_accepted"] == 1
    assert data["rows_rejected"] == 1
    assert data["rows_ignored"] == 0

def test_ohlcv_preview_quote_slb_rejected():
    csv_content = """Symbol,Date,Settlement Date,Series,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","30-JUL-2026","01-SEP-2026","X9","4.90","4.90","4.90","4.90","7"
"""
    response = client.post("/api/ohlcv/preview", files={"file": ("Quote-SLB-ADANIENT-EQ.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")})
    assert response.status_code == 400
    assert "Quote-SLB" in response.json()["detail"]


def test_ohlcv_preview_udiff_eq_and_non_eq():
    csv_content = """TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol
2026-08-12,ADANIENT,EQ,3000,3050,2950,3020,100000
2026-08-12,ADANIENT,BL,3000,3050,2950,3020,50
"""
    response = client.post("/api/ohlcv/preview", files={"file": ("udiff.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["rows_received"] == 2
    assert data["rows_accepted"] == 1
    assert data["rows_ignored"] == 1


def test_ohlcv_confirm_conflict():
    from app.services.ohlcv_service import OhlcvService
    from app.schemas.ohlcv import OhlcvConfirmRequest

    first = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","EQ","13-Aug-2026","3000","3050","2950","3020","100000"
"""
    conflict = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","EQ","13-Aug-2026","3100","3150","3050","3120","200000"
"""
    db = TestingSessionLocal()
    try:
        req = OhlcvConfirmRequest(file_sha256="dummy", original_filename="a.csv", source_name="NSE")
        OhlcvService.confirm_import(db, req, first.encode("utf-8"))
        preview = OhlcvService.parse_historical_file(db, conflict.encode("utf-8"), "b.csv")
        assert preview.rows_conflicts == 1
        assert preview.rows_accepted == 0
    finally:
        db.close()


def test_ohlcv_confirm_import_idempotency():
    from app.services.ohlcv_service import OhlcvService
    from app.schemas.ohlcv import OhlcvConfirmRequest
    
    csv_content = """Symbol,Series,Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity
"ADANIENT","EQ","13-Aug-2026","3000","3050","2950","3020","100000"
"""
    req = OhlcvConfirmRequest(file_sha256="dummy", original_filename="test.csv", source_name="NSE")
    db = TestingSessionLocal()
    try:
        # First import
        res1 = OhlcvService.confirm_import(db, req, csv_content.encode('utf-8'))
        assert res1["rows_accepted"] == 1
        assert res1["rows_rejected"] == 0
        
        # Second import (duplicate)
        res2 = OhlcvService.confirm_import(db, req, csv_content.encode('utf-8'))
        assert res2["rows_accepted"] == 0
        assert res2["rows_rejected"] == 0 # Idempotency policy: skip duplicates quietly without rejecting if identical
    finally:
        db.close()
