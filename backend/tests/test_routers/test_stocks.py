import pytest

def test_stock_master_endpoints(client):
    # 1. Create valid stock & 2. Symbol converted to uppercase
    res = client.post("/api/stocks", json={
        "nse_symbol": " reliance_api ",
        "company_name": "Reliance Ind API"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["nse_symbol"] == "RELIANCE_API"
    stock_id = data["stock_id"]

    # 3. Duplicate NSE symbol rejected
    res = client.post("/api/stocks", json={
        "nse_symbol": "RELIANCE_API",
        "company_name": "Reliance 2"
    })
    assert res.status_code == 409

    # Create another stock with ISIN
    res = client.post("/api/stocks", json={
        "nse_symbol": "TCS_API",
        "company_name": "TCS Ltd API",
        "isin": "INE002A01019"
    })
    assert res.status_code == 200

    # 4. Duplicate non-null ISIN rejected
    res = client.post("/api/stocks", json={
        "nse_symbol": "INFY_API",
        "company_name": "Infy",
        "isin": "ine002a01019"
    })
    assert res.status_code == 409

    # 5. Search by symbol & 6. Search by company name
    res = client.get("/api/stocks?q=relian")
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert any(s["nse_symbol"] == "RELIANCE_API" for s in res.json())

    res = client.get("/api/stocks?q=tcs")
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert any(s["nse_symbol"] == "TCS_API" for s in res.json())

    # 7. Update stock & 8. Deactivate stock without deleting history
    res = client.put(f"/api/stocks/{stock_id}", json={
        "listing_status": "INACTIVE"
    })
    assert res.status_code == 200
    assert res.json()["listing_status"] == "INACTIVE"
    
    # 49. Stock endpoints tests complete
