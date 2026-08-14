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

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    from app.models import StockMaster, DailyOhlcv, DataImportBatch
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add(StockMaster(nse_symbol="ADANIENT", company_name="Adani Ent", listing_status="ACTIVE"))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)

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
