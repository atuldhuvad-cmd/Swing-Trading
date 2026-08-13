import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime
import json
import io

from app.models import ImportBatch, ImportBatchDetail, BrokerRecommendation, SourceReference, StockMaster, BrokerMaster
from app.main import app

def test_upload_csv(client, db_session: Session):
    csv_content = "nse_symbol,broker,date,rating,target\nRELIANCE,HDFC,2024-01-01,BUY,3000\n"
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'test.csv'
    
    response = client.post("/api/imports/upload", files={"file": ("test.csv", file, "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "test.csv"
    assert "nse_symbol" in data["detected_headers"]
    assert len(data["preview_rows"]) == 1

def test_apply_mapping(client, db_session: Session):
    # Setup
    csv_content = "sym,brk,dt,rt,tgt,stype,url\nRELIANCE,HDFC Securities,2024-01-01,BUY,3000,BROKER_RESEARCH,http://test.com\n"
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'test.csv'
    upload_res = client.post("/api/imports/upload", files={"file": ("test.csv", file, "text/csv")})
    batch_id = upload_res.json()["batch_id"]

    mapping = {
        "mapping": {
            "nse_symbol": "sym",
            "broker_name": "brk",
            "recommendation_date": "dt",
            "original_rating": "rt",
            "target_price": "tgt",
            "source_type": "stype",
            "source_url": "url"
        }
    }
    map_res = client.post(f"/api/imports/{batch_id}/mapping", json=mapping)
    assert map_res.status_code == 200
    data = map_res.json()
    assert data["total_rows"] == 1
    assert data["valid_unique"] == 1
    assert data["rows"][0]["action"] == "UNIQUE"

    # Confirm
    confirm_res = client.post(f"/api/imports/{batch_id}/confirm")
    assert confirm_res.status_code == 200
    
    # Check if record exists
    rec = db_session.query(BrokerRecommendation).first()
    assert rec is not None
    stock = db_session.query(StockMaster).filter_by(stock_id=rec.stock_id).first()
    assert stock.nse_symbol == "RELIANCE"
    broker = db_session.query(BrokerMaster).filter_by(broker_id=rec.broker_id).first()
    assert broker.display_name == "HDFC Securities"
