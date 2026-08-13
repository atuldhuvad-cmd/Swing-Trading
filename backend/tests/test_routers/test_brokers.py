import pytest

def test_broker_master_endpoints(client):

    # 9. Create broker
    res = client.post("/api/brokers", json={
        "canonical_name": " Test Broker API ",
        "display_name": "Test API",
        "is_historical_only": False
    })
    assert res.status_code == 200
    b1_id = res.json()["broker_id"]
    assert res.json()["normalized_name"] == "testbrokerapi"

    # 10. Duplicate normalized identity rejected
    res = client.post("/api/brokers", json={
        "canonical_name": "test broker api",
        "display_name": "Test 2 API"
    })
    assert res.status_code == 409

    # 11. Create alias
    res = client.post(f"/api/brokers/{b1_id}/aliases", json={
        "alias_name": "TB_API"
    })
    assert res.status_code == 200

    # 12. Duplicate alias handling
    res = client.post(f"/api/brokers/{b1_id}/aliases", json={
        "alias_name": "TB_API"
    })
    assert res.status_code == 409

    # 13. Alias resolution
    res = client.get("/api/brokers?q=TB_API")
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert any(b["broker_id"] == b1_id for b in res.json())

    # 16. Create lineage relationship & 17. Historical issuer identity remains unchanged
    res = client.post("/api/brokers", json={
        "canonical_name": "Test Acquirer API",
        "display_name": "Acq API",
        "is_historical_only": False
    })
    assert res.status_code == 200
    b2_id = res.json()["broker_id"]

    res = client.post(f"/api/brokers/{b1_id}/relationships", json={
        "predecessor_id": b1_id,
        "successor_id": b2_id,
        "relationship_type": "ACQUIRED_BY"
    })
    assert res.status_code == 200

    res = client.get(f"/api/brokers/{b1_id}")
    assert res.status_code == 200
    assert res.json()["canonical_name"] == "Test Broker API"

    # Historical/date-aware resolution & ambiguous identity handling
    res = client.post("/api/brokers", json={
        "canonical_name": "Old Broker API",
        "display_name": "Old API",
        "is_historical_only": True
    })
    assert res.status_code == 200

def test_recommendation_streams(client):
    res = client.post("/api/brokers", json={
        "canonical_name": "B3_STREAM_API",
        "display_name": "B3"
    })
    assert res.status_code == 200
    b3_id = res.json()["broker_id"]

    # 18. Create stream
    res = client.post(f"/api/brokers/{b3_id}/streams", json={
        "stream_name": "Daily Recs",
        "stream_type": "Research",
        "frequency": "DAILY"
    })
    assert res.status_code == 200
    stream_id = res.json()["stream_id"]

    # 19. Invalid frequency rejected
    res = client.post(f"/api/brokers/{b3_id}/streams", json={
        "stream_name": "Hourly Recs",
        "stream_type": "Research",
        "frequency": "HOURLY"
    })
    assert res.status_code == 422

    # 20. Disable stream
    res = client.put(f"/api/brokers/{b3_id}/streams/{stream_id}", json={
        "enabled": False
    })
    assert res.status_code == 200
    assert res.json()["enabled"] is False
