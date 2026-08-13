import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import io
from app.main import app
import openpyxl

client = TestClient(app)

def create_test_excel():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["nse_symbol", "broker", "target"])
    ws.append(["RELIANCE", "HDFC", 3000])
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    out.name = 'test.xlsx'
    return out

def test_valid_xlsx(db_session: Session):
    file = create_test_excel()
    res = client.post("/api/imports/upload", files={"file": ("test.xlsx", file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert res.status_code == 200
    assert "nse_symbol" in res.json()["detected_headers"]

def test_empty_xlsx(db_session: Session):
    wb = openpyxl.Workbook()
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    out.name = 'empty.xlsx'
    res = client.post("/api/imports/upload", files={"file": ("empty.xlsx", out, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert res.status_code == 400
    assert "no headers" in res.json()["detail"].lower() or "empty" in res.json()["detail"].lower()

def test_unsupported_xls(db_session: Session):
    file = io.BytesIO(b'dummy xls data')
    file.name = 'test.xls'
    res = client.post("/api/imports/upload", files={"file": ("test.xls", file, "application/vnd.ms-excel")})
    assert res.status_code == 400

def test_malformed_xlsx(db_session: Session):
    file = io.BytesIO(b'malformed xlsx data')
    file.name = 'malformed.xlsx'
    res = client.post("/api/imports/upload", files={"file": ("malformed.xlsx", file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert res.status_code == 400
