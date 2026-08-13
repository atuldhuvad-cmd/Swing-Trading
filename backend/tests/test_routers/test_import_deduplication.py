import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import io
from app.main import app
from app.models import BrokerRecommendation, SourceReference
import datetime

def run_mapping(client, csv_content):
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'test.csv'
    res = client.post("/api/imports/upload", files={"file": ("test.csv", file, "text/csv")})
    batch_id = res.json()["batch_id"]
    
    mapping = {
        "mapping": {
            "nse_symbol": "sym",
            "broker_name": "brk",
            "recommendation_date": "dt",
            "original_rating": "rt",
            "target_price": "tgt",
            "source_url": "url",
            "source_type": "stype"
        }
    }
    map_res = client.post(f"/api/imports/{batch_id}/mapping", json=mapping)
    return map_res.json()["rows"], batch_id

def seed_recommendation(client, db_session):
    csv = "sym,brk,dt,rt,tgt,url,stype\nRELIANCE,HDFC Securities,2024-01-01,BUY,3000,http://test.com,BROKER_RESEARCH\n"
    rows, batch_id = run_mapping(client, csv)
    from app.services.import_service import ImportService
    ImportService.confirm_batch(db_session, int(batch_id))

def test_exact_duplicate(client, db_session: Session):
    seed_recommendation(client, db_session)
    csv = "sym,brk,dt,rt,tgt,url,stype\nRELIANCE,HDFC Securities,2024-01-01,BUY,3000,http://test.com,BROKER_RESEARCH\n"
    rows, _ = run_mapping(client, csv)
    assert rows[0]["action"] == "EXACT_DUPLICATE"

def test_attach_source(client, db_session: Session):
    seed_recommendation(client, db_session)
    csv = "sym,brk,dt,rt,tgt,url,stype\nRELIANCE,HDFC Securities,2024-01-01,BUY,3000,http://newsource.com,BROKER_RESEARCH\n"
    rows, _ = run_mapping(client, csv)
    assert rows[0]["action"] == "ATTACH_SOURCE"

def test_duplicate_within_batch(client, db_session: Session):
    # No seed needed, checking intra-batch
    csv = "sym,brk,dt,rt,tgt,url,stype\nRELIANCE,HDFC Securities,2024-06-01,BUY,3000,http://url1.com,BROKER_RESEARCH\nRELIANCE,HDFC Securities,2024-06-01,BUY,3000,http://url2.com,BROKER_RESEARCH\n"
    rows, _ = run_mapping(client, csv)
    assert rows[0]["action"] == "UNIQUE"
    assert rows[1]["action"] == "DUPLICATE_IN_BATCH" 

def test_probable_duplicate(client, db_session: Session):
    seed_recommendation(client, db_session)
    # Different date (within 7 days) but same rating = PROBABLE_DUPLICATE
    csv = "sym,brk,dt,rt,tgt,url,stype\nRELIANCE,HDFC Securities,2024-01-02,BUY,3050,http://url1.com,BROKER_RESEARCH\n"
    rows, _ = run_mapping(client, csv)
    assert rows[0]["action"] == "PROBABLE_DUPLICATE"

def test_possible_update(client, db_session: Session):
    seed_recommendation(client, db_session)
    # Different date (within 7 days) AND different rating = POSSIBLE_UPDATE
    # We must seed HOLD rating in conftest too if we use HOLD, or just use another rating. 
    # Let's use SELL and add it to conftest
    csv = "sym,brk,dt,rt,tgt,url,stype\nRELIANCE,HDFC Securities,2024-01-05,SELL,3500,http://url1.com,BROKER_RESEARCH\n"
    rows, _ = run_mapping(client, csv)
    assert rows[0]["action"] == "POSSIBLE_UPDATE"

def test_different_broker(client, db_session: Session):
    seed_recommendation(client, db_session)
    csv = "sym,brk,dt,rt,tgt,url,stype\nRELIANCE,ICICI Direct,2024-01-01,BUY,3000,http://url1.com,BROKER_RESEARCH\n"
    rows, _ = run_mapping(client, csv)
    assert rows[0]["action"] == "UNIQUE"
