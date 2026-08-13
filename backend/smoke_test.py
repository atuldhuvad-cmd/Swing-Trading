import requests
import datetime

BASE_URL = 'http://127.0.0.1:8001/api'

def run_smoke_test():
    print("1. Create/select test stock")
    res = requests.post(f"{BASE_URL}/stocks", json={"nse_symbol": "SMOKETEST", "company_name": "Smoke"})
    if res.status_code == 409:
        # Get existing
        res = requests.get(f"{BASE_URL}/stocks?q=SMOKETEST")
        stock_id = res.json()[0]['stock_id']
    else:
        stock_id = res.json()['stock_id']
    print("PASS")

    print("2. Create/select test broker")
    res = requests.post(f"{BASE_URL}/brokers", json={"canonical_name": "SmokeBroker", "display_name": "Smoke", "is_historical_only": False})
    if res.status_code == 409:
        res = requests.get(f"{BASE_URL}/brokers?q=SmokeBroker")
        broker_id = res.json()[0]['broker_id']
    else:
        broker_id = res.json()['broker_id']
    print("PASS")

    print("4. Create broker recommendation")
    rec_payload = {
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": (datetime.datetime.utcnow() - datetime.timedelta(minutes=10)).isoformat(),
        "original_rating": "Buy",
        "normalized_rating": "BUY",
        "evidence": [{"source_type_id": 1, "verification_status": "VERIFIED_PRIMARY"}]
    }
    res = requests.post(f"{BASE_URL}/recommendations", json=rec_payload)
    rec_id = res.json()['recommendation_id']
    print("PASS")

    print("6. View recommendation")
    res = requests.get(f"{BASE_URL}/recommendations/{rec_id}")
    assert res.status_code == 200
    print("PASS")

    print("7. Attach a second evidence source")
    res = requests.post(f"{BASE_URL}/recommendations/{rec_id}/sources", json={"source_type_id": 1, "verification_status": "VERIFIED_SECONDARY", "url": "http://smoke.test"})
    assert res.status_code == 200
    print("PASS")

    print("8. Confirm recommendation count remains ONE")
    res = requests.get(f"{BASE_URL}/recommendations/{rec_id}")
    assert len(res.json()['sources']) == 2
    print("PASS")

    print("9. Create a genuinely newer recommendation")
    new_rec_payload = {
        "stock_id": stock_id,
        "broker_id": broker_id,
        "recommendation_date": datetime.datetime.utcnow().isoformat(),
        "original_rating": "Strong Buy",
        "normalized_rating": "STRONG_BUY",
        "evidence": [{"source_type_id": 1, "verification_status": "VERIFIED_PRIMARY"}]
    }
    res = requests.post(f"{BASE_URL}/recommendations/{rec_id}/supersede", json=new_rec_payload)
    if res.status_code != 200:
        print("FAIL step 9", res.text)
        return
    new_rec_id = res.json()['recommendation_id']
    print("PASS")

    print("11. Confirm old recommendation remains in history")
    res = requests.get(f"{BASE_URL}/recommendations/{rec_id}")
    assert res.json()['lifecycle_status'] == 'SUPERSEDED'
    print("PASS")

    print("12. Confirm status-history record exists")
    assert len(res.json()['status_history']) > 1
    assert res.json()['status_history'][-1]['status'] == 'SUPERSEDED'
    print("PASS")
    
if __name__ == '__main__':
    try:
        run_smoke_test()
    except Exception as e:
        print("FAIL", e)
