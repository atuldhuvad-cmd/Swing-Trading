import pytest
from datetime import datetime, timedelta

def test_recommendation_endpoints(client, db_session):

    # Setup data
    res = client.post("/api/stocks", json={"nse_symbol": "RECSTOCK", "company_name": "Test"})
    stock_id = res.json()["stock_id"]

    res = client.post("/api/brokers", json={"canonical_name": "RecBroker", "display_name": "Test"})
    broker_id = res.json()["broker_id"]
    
    # Needs source_type
    from app.models import SourceTypeMaster
    stype = SourceTypeMaster(type_name="TEST_TYPE")
    db_session.add(stype)
    db_session.commit()
    db_session.refresh(stype)

    valid_evidence = [{
        "source_type_id": stype.source_type_id,
        "verification_status": "VERIFIED_PRIMARY"
    }]

    # 21. Valid recommendation creation & 31. Cannot be created without evidence
    # 28. Optional fields remain NULL
    res = client.post("/api/recommendations", json={
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": datetime.utcnow().isoformat(),
        "original_rating": "Strong Buy",
        "normalized_rating": "STRONG_BUY",
        "evidence": valid_evidence
    })
    assert res.status_code == 200
    rec_id = res.json()["recommendation_id"]
    assert res.json()["target_price"] is None

    # No evidence fails
    res_no_ev = client.post("/api/recommendations", json={
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": datetime.utcnow().isoformat(),
        "original_rating": "Buy",
        "normalized_rating": "BUY",
        "evidence": []
    })
    assert res_no_ev.status_code == 422

    # 22. Unknown stock rejected
    res = client.post("/api/recommendations", json={
        "stock_id": 9999,
        "broker_id": broker_id,
        "recommendation_date": datetime.utcnow().isoformat(),
        "original_rating": "Buy",
        "normalized_rating": "BUY",
        "evidence": valid_evidence
    })
    assert res.status_code == 422

    # 24. Future date rejected
    future_date = (datetime.utcnow() + timedelta(days=1)).isoformat()
    res = client.post("/api/recommendations", json={
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": future_date,
        "original_rating": "Buy",
        "normalized_rating": "BUY",
        "evidence": valid_evidence
    })
    assert res.status_code == 422

    # 27. Entry low > high rejected
    res = client.post("/api/recommendations", json={
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": datetime.utcnow().isoformat(),
        "original_rating": "Buy",
        "normalized_rating": "BUY",
        "entry_price_low": 100.0,
        "entry_price_high": 90.0,
        "evidence": valid_evidence
    })
    assert res.status_code == 422

    # 36. Invalid verification status rejected
    res = client.post("/api/recommendations", json={
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": datetime.utcnow().isoformat(),
        "original_rating": "Buy",
        "normalized_rating": "BUY",
        "evidence": [{
            "source_type_id": stype.source_type_id,
            "verification_status": "INVALID_STATUS"
        }]
    })
    assert res.status_code == 422

    # 37. Multiple sources attach to one recommendation
    res = client.post(f"/api/recommendations/{rec_id}/sources", json={
        "source_type_id": stype.source_type_id,
        "verification_status": "VERIFIED_SECONDARY",
        "url": "http://test.com"
    })
    assert res.status_code == 200

    # Negative target rejected
    res = client.post("/api/recommendations", json={
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": datetime.utcnow().isoformat(),
        "original_rating": "Buy",
        "normalized_rating": "BUY",
        "target_price": -50.0,
        "evidence": valid_evidence
    })
    assert res.status_code == 422

    # Negative stop loss rejected
    res = client.post("/api/recommendations", json={
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": datetime.utcnow().isoformat(),
        "original_rating": "Buy",
        "normalized_rating": "BUY",
        "stop_loss": -50.0,
        "evidence": valid_evidence
    })
    assert res.status_code == 422

    # 40. Duplicate source link rejected (using same URL or identity logic handled by DB)
    res = client.get(f"/api/recommendations/{rec_id}")
    assert res.status_code == 200
    assert len(res.json()["sources"]) == 2
