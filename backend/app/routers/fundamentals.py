from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.fundamental import FundamentalManualImport, FundamentalConfirmRequest
from app.services.fundamental_catalog import catalog_payload
from app.services.fundamental_import_service import FundamentalImportService

router = APIRouter(prefix="/api/fundamentals", tags=["fundamentals"])


@router.get("/catalog")
def get_fundamental_catalog():
    return catalog_payload()


@router.post("/preview")
def preview_fundamental_import(payload: FundamentalManualImport, db: Session = Depends(get_db)):
    try:
        return FundamentalImportService.preview(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm")
def confirm_fundamental_import(req: FundamentalConfirmRequest, db: Session = Depends(get_db)):
    try:
        return FundamentalImportService.confirm(db, req.payload, req.payload_sha256)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
