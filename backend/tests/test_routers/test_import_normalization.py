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


def test_date_format_day_month_name_year(client, db_session: Session):
    csv = "sym,brk,dt,rt,tgt,elow,ehigh,stype\nRELIANCE,HDFC Securities,31 Aug 2026,BUY,3000,,,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "UNIQUE"
    assert row["mapped_data"]["recommendation_date"].startswith("2026-08-31")

def test_date_placeholder_current_note(client, db_session: Session):
    csv = "sym,brk,dt,rt,tgt,elow,ehigh,stype\nRELIANCE,HDFC Securities,Current note,BUY,3000,,,BROKER_RESEARCH\n"
    row = run_mapping(client, csv)
    assert row["action"] == "UNIQUE"
    # Resolved to today's date rather than rejected outright
    assert row["mapped_data"]["recommendation_date"].startswith(datetime.date.today().isoformat())

def test_default_source_type_applies_when_no_column(client, db_session: Session):
    # File has no source-type column at all -- a weekly compiled file like
    # this is entirely one kind of source, so a batch-level default should
    # be used instead of flagging every row for manual review.
    file = io.BytesIO(b"sym,brk,dt,rt,tgt,elow,ehigh\nRELIANCE,HDFC Securities,2024-05-01,BUY,3000,,\n")
    file.name = 'test.csv'
    res = client.post("/api/imports/upload", files={"file": ("test.csv", file, "text/csv")})
    batch_id = res.json()["batch_id"]
    mapping = {
        "mapping": {
            "nse_symbol": "sym", "broker_name": "brk", "recommendation_date": "dt",
            "original_rating": "rt", "target_price": "tgt",
            "entry_price_low": "elow", "entry_price_high": "ehigh",
            "default_source_type": "BROKER_RESEARCH",
        }
    }
    map_res = client.post(f"/api/imports/{batch_id}/mapping", json=mapping)
    row = map_res.json()["rows"][0]
    assert row["action"] == "UNIQUE"
    assert row["mapped_data"]["source_type_id"] is not None

    confirm_res = client.post(f"/api/imports/{batch_id}/confirm")
    assert confirm_res.status_code == 200

def test_missing_source_type_does_not_crash_confirm(client, db_session: Session):
    # No source-type column and no default -- normalize_row correctly
    # flags this REVIEW_REQUIRED. Force it back to UNIQUE the way the
    # Review Queue's "Accept As New" does, to exercise confirm_batch's
    # defensive guard: it must reject the row cleanly instead of hitting
    # the NOT NULL constraint on source_reference.source_type_id.
    file = io.BytesIO(b"sym,brk,dt,rt,tgt\nRELIANCE,HDFC Securities,2024-05-01,BUY,3000\n")
    file.name = 'test.csv'
    res = client.post("/api/imports/upload", files={"file": ("test.csv", file, "text/csv")})
    batch_id = res.json()["batch_id"]
    mapping = {"mapping": {"nse_symbol": "sym", "broker_name": "brk", "recommendation_date": "dt", "original_rating": "rt", "target_price": "tgt"}}
    map_res = client.post(f"/api/imports/{batch_id}/mapping", json=mapping)
    row = map_res.json()["rows"][0]
    assert row["action"] == "REVIEW_REQUIRED"
    assert row["mapped_data"].get("source_type_id") is None

    from app.models import ImportBatchDetail
    detail = db_session.query(ImportBatchDetail).filter(ImportBatchDetail.batch_id == batch_id).first()
    detail.action = 'UNIQUE'
    detail.status = 'PREVIEW'
    db_session.commit()

    confirm_res = client.post(f"/api/imports/{batch_id}/confirm")
    assert confirm_res.status_code == 200  # must not 500

    db_session.refresh(detail)
    assert detail.status == 'REJECTED'
    assert 'source type' in (detail.error_message or '').lower()
