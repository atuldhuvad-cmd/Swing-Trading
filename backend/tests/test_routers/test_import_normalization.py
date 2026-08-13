from sqlalchemy.orm import Session
import io
from app.models import StockMaster, BrokerMaster, BrokerAlias
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
            "entry_price_low": "elow",
            "entry_price_high": "ehigh",
            "source_type": "stype"
        }
    }
    map_res = client.post(f"/api/imports/{batch_id}/mapping", json=mapping)
    return map_res.json()["rows"][0]

def test_nse_symbol_uppercase(client, db_session: Session):
    csv = "sym,brk,dt,rt,tgt,elow,ehigh,stype\nreliance,HDFC Securities,2024-05-01,BUY,3000,,,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "UNIQUE"
    
def test_unknown_stock(client, db_session: Session):
    csv = "sym,brk,dt,rt,tgt,elow,ehigh,stype\nUNKNOWNSTK,HDFC Securities,2024-05-01,BUY,3000,,,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "UNKNOWN_STOCK"

def test_broker_canonical(client, db_session: Session):
    csv = "sym,brk,dt,rt,tgt,elow,ehigh,stype\nRELIANCE,HDFC Securities,2024-05-01,BUY,3000,,,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "UNIQUE"

def test_broker_alias(client, db_session: Session):
    # Setup alias
    b = db_session.query(BrokerMaster).filter(BrokerMaster.display_name == 'HDFC Securities').first()
    if b:
        db_session.add(BrokerAlias(broker_id=b.broker_id, alias_name='HDFC Sec'))
        db_session.commit()
    
    csv = "sym,brk,dt,rt,tgt,elow,ehigh,stype\nRELIANCE,HDFC Sec,2024-05-01,BUY,3000,,,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "UNIQUE"

def test_unknown_broker(client, db_session: Session):
    csv = "sym,brk,dt,rt,tgt,elow,ehigh,stype\nRELIANCE,Ghost Broker,2024-05-01,BUY,3000,,,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "UNKNOWN_BROKER"

def test_price_normalization(client, db_session: Session):
    csv = 'sym,brk,dt,rt,tgt,elow,ehigh,stype\nRELIANCE,HDFC Securities,2024-05-01,BUY,"₹ 3,000",,,BROKER_RESEARCH\n'
    row = run_mapping(client, csv)
    assert row["action"] == "UNIQUE"

def test_future_date_rejected(client, db_session: Session):
    future_date = (datetime.datetime.now() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    csv = f"sym,brk,dt,rt,tgt,elow,ehigh,stype\nRELIANCE,HDFC Securities,{future_date},BUY,3000,,,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "INVALID"

def test_entry_low_high(client, db_session: Session):
    csv = "sym,brk,dt,rt,tgt,elow,ehigh,stype\nRELIANCE,HDFC Securities,2024-05-01,BUY,3000,300,200,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "INVALID"
    assert "Entry low" in row["error_message"]
