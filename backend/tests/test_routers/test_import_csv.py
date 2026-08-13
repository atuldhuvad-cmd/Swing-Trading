from sqlalchemy.orm import Session
import io

def test_valid_csv(client, db_session: Session):
    csv_content = "nse_symbol,broker,date,rating,target\nRELIANCE,HDFC,2024-01-01,BUY,3000\n"
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'test.csv'
    res = client.post("/api/imports/upload", files={"file": ("test.csv", file, "text/csv")})
    assert res.status_code == 200
    assert len(res.json()["preview_rows"]) == 1

def test_utf8_bom_csv(client, db_session: Session):
    csv_content = "\ufeffnse_symbol,broker,date\nRELIANCE,HDFC,2024-01-01\n"
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'bom.csv'
    res = client.post("/api/imports/upload", files={"file": ("bom.csv", file, "text/csv")})
    assert res.status_code == 200
    assert "nse_symbol" in res.json()["detected_headers"]

def test_quoted_comma_csv(client, db_session: Session):
    csv_content = 'nse_symbol,broker,target\nRELIANCE,"HDFC, Inc.",3000\n'
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'quotes.csv'
    res = client.post("/api/imports/upload", files={"file": ("quotes.csv", file, "text/csv")})
    assert res.status_code == 200
    assert res.json()["preview_rows"][0]["broker"] == "HDFC, Inc."

def test_empty_values_csv(client, db_session: Session):
    csv_content = 'nse_symbol,broker,target,stop_loss\nRELIANCE,HDFC,3000,\n'
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'empty.csv'
    res = client.post("/api/imports/upload", files={"file": ("empty.csv", file, "text/csv")})
    assert res.status_code == 200
    assert res.json()["preview_rows"][0]["stop_loss"] == ""

def test_na_values_csv(client, db_session: Session):
    csv_content = 'nse_symbol,broker,target,stop_loss\nRELIANCE,HDFC,N/A,NA\n'
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'na.csv'
    res = client.post("/api/imports/upload", files={"file": ("na.csv", file, "text/csv")})
    assert res.status_code == 200
    # The normalization handles NA, upload just previews exactly as written
    assert res.json()["preview_rows"][0]["target"] == "N/A"

def test_missing_required_headers(client, db_session: Session):
    # Actually upload doesn't strictly validate headers, mapping does.
    # We will test mapping with missing fields.
    csv_content = "sym\nRELIANCE\n"
    file = io.BytesIO(csv_content.encode('utf-8'))
    file.name = 'missing.csv'
    upload_res = client.post("/api/imports/upload", files={"file": ("missing.csv", file, "text/csv")})
    batch_id = upload_res.json()["batch_id"]
    
    mapping = {"mapping": {"nse_symbol": "sym"}} # missing broker_name etc
    map_res = client.post(f"/api/imports/{batch_id}/mapping", json=mapping)
    assert map_res.status_code == 200
    assert map_res.json()["rows"][0]["action"] == "INVALID"
