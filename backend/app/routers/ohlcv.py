from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.ohlcv_service import OhlcvService
from app.schemas.ohlcv import OhlcvPreviewResponse, OhlcvConfirmRequest

router = APIRouter(prefix="/api/ohlcv", tags=["OHLCV"])

@router.post("/preview", response_model=OhlcvPreviewResponse)
async def preview_ohlcv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(400, "Only .csv files are supported")
    
    contents = await file.read()
    try:
        response = OhlcvService.parse_historical_file(db, contents, file.filename)
        return response
    except Exception as e:
        print(f"Exception in preview: {e}")
        raise HTTPException(400, f"Error parsing file: {e}")

@router.post("/confirm")
async def confirm_ohlcv(req: OhlcvConfirmRequest = Depends(), file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(400, "Only .csv files are supported")
    contents = await file.read()
    try:
        return OhlcvService.confirm_import(db, req, contents)
    except Exception as e:
        raise HTTPException(400, f"Error confirming import: {e}")
