import sys
import os
import io
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.database import Base, get_db
from app.models import StockMaster, BrokerMaster, SourceTypeMaster, RatingNormalization, ImportBatch

# 1. Isolated Temp DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/temp_smoke_test.db"
if os.path.exists("./data/temp_smoke_test.db"):
    os.remove("./data/temp_smoke_test.db")

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        # Enforce foreign keys manually for sqlite if needed, but our migrations tests already check it.
        db.execute(__import__('sqlalchemy').text("PRAGMA foreign_keys=ON"))
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

db = TestingSessionLocal()

try:
    print("Step 1 & 2 & 3: Setup Masters")
    db.add(StockMaster(nse_symbol='SMOKESTOCK', company_name='Smoke Test Inc'))
    db.add(BrokerMaster(display_name='Smoke Broker', canonical_name='Smoke Broker', normalized_name='SMOKE BROKER'))
    db.add(SourceTypeMaster(type_name='BROKER_RESEARCH'))
    db.add(RatingNormalization(original_rating='BUY', normalized_rating='BUY'))
    db.commit()

    print("Step 4 & 5: Upload CSV")
    csv1 = "sym,brk,dt,rt,tgt,stype,url\nSMOKESTOCK,Smoke Broker,2024-01-01,BUY,3000,BROKER_RESEARCH,http://test1.com\n"
    f1 = io.BytesIO(csv1.encode('utf-8'))
    f1.name = "smoke1.csv"
    res = client.post("/api/imports/upload", files={"file": ("smoke1.csv", f1, "text/csv")})
    assert res.status_code == 200, res.text
    batch1_id = res.json()["batch_id"]

    print("Step 6 & 7: Mapping and Preview")
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
    res = client.post(f"/api/imports/{batch1_id}/mapping", json=mapping)
    assert res.status_code == 200, res.text
    assert res.json()["rows"][0]["action"] == "UNIQUE"
    
    print("Step 8: Confirm zero recommendations before confirm")
    res = client.get("/api/recommendations/")
    assert len(res.json()) == 0

    print("Step 9 & 10 & 11: Confirm Import 1")
    res = client.post(f"/api/imports/{batch1_id}/confirm")
    assert res.status_code == 200, res.text
    
    res = client.get("/api/recommendations/")
    recs = res.json()
    assert len(recs) == 1
    rec1_id = recs[0]["recommendation_id"]
    print(f"  -> First confirmed import recommendation count: {len(recs)}")

    # Check sources
    from app.models import BrokerRecommendation, SourceReference
    sources1 = db.query(SourceReference).count()
    assert sources1 == 1
    print(f"  -> First confirmed source count: {sources1}")

    print("Step 12 & 13: Upload 2nd CSV (same rec, different source URL)")
    csv2 = "sym,brk,dt,rt,tgt,stype,url\nSMOKESTOCK,Smoke Broker,2024-01-01,BUY,3000,BROKER_RESEARCH,http://test2.com\n"
    f2 = io.BytesIO(csv2.encode('utf-8'))
    f2.name = "smoke2.csv"
    res = client.post("/api/imports/upload", files={"file": ("smoke2.csv", f2, "text/csv")})
    batch2_id = res.json()["batch_id"]
    res = client.post(f"/api/imports/{batch2_id}/mapping", json=mapping)
    assert res.json()["rows"][0]["action"] == "ATTACH_SOURCE"
    res = client.post(f"/api/imports/{batch2_id}/confirm")
    assert res.status_code == 200

    print("Step 14: Verify counts after 2nd import")
    res = client.get("/api/recommendations/")
    recs2 = res.json()
    assert len(recs2) == 1
    print(f"  -> After second-source import recommendation count: {len(recs2)}")
    sources2 = db.query(SourceReference).count()
    assert sources2 == 2
    print(f"  -> After second-source import source count: {sources2}")

    print("Step 15 & 16 & 17: Import Probable Duplicate (Review Queue)")
    csv3 = "sym,brk,dt,rt,tgt,stype,url\nSMOKESTOCK,Smoke Broker,2024-01-02,BUY,3000,BROKER_RESEARCH,http://test3.com\n"
    f3 = io.BytesIO(csv3.encode('utf-8'))
    f3.name = "smoke3.csv"
    res = client.post("/api/imports/upload", files={"file": ("smoke3.csv", f3, "text/csv")})
    batch3_id = res.json()["batch_id"]
    res = client.post(f"/api/imports/{batch3_id}/mapping", json=mapping)
    assert res.json()["rows"][0]["action"] == "PROBABLE_DUPLICATE"
    res = client.post(f"/api/imports/{batch3_id}/confirm")
    assert res.status_code == 200

    # check review queue
    res = client.get("/api/review")
    reviews = res.json()
    if not isinstance(reviews, list):
        print(reviews)
    assert len(reviews) == 1
    print("  -> Review Queue case: PASS")
    review_id = reviews[0]["review_id"]
    # resolve it as UNIQUE
    res = client.post(f"/api/review/{review_id}/resolve", json={"action": "ACCEPT_AS_NEW"})
    assert res.status_code == 200, res.text

    print("Step 18: Inspect Import History")
    res = client.get("/api/imports")
    history = res.json()
    assert len(history) == 3, f"Expected 3, got {history}"
    print("  -> Import History: PASS")

    print("Step 19 & 20: Rollback the 2nd batch")
    res = client.post(f"/api/imports/{batch2_id}/rollback")
    assert res.status_code == 200
    print("  -> Rollback: PASS")
    
    res = client.get("/api/recommendations/")
    recs = res.json()
    assert len(recs) == 2, f"Expected 2, got {len(recs)}: {recs}"
    print("  -> Original recommendation survives rollback: PASS")
    
    sources3 = db.query(SourceReference).count()
    assert sources3 == 2 # 1 from batch 1, 1 from batch 3 (batch 2 source is gone)
    print("  -> Original source survives rollback: PASS")
    print("  -> Batch-added source removed/voided safely: PASS")

    print("Step 21 & 22: Re-import 1st file (idempotency)")
    f4 = io.BytesIO(csv1.encode('utf-8'))
    f4.name = "smoke4.csv"
    res = client.post("/api/imports/upload", files={"file": ("smoke4.csv", f4, "text/csv")})
    batch4_id = res.json()["batch_id"]
    res = client.post(f"/api/imports/{batch4_id}/mapping", json=mapping)
    assert res.json()["rows"][0]["action"] == "EXACT_DUPLICATE"
    res = client.post(f"/api/imports/{batch4_id}/confirm")
    assert res.status_code == 200
    
    res = client.get("/api/recommendations/")
    assert len(res.json()) == 2
    print("  -> Re-import idempotency: PASS")

    print("SMOKE WORKFLOW PASSED")
finally:
    db.close()
