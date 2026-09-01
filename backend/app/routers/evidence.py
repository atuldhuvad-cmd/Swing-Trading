from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import StockMaster
from app.services.evidence_service import EvidenceService

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


@router.get("/candidates")
def list_candidate_evidence(db: Session = Depends(get_db)):
    return {"items": EvidenceService.list_candidates(db)}


@router.get("/market-data")
def market_data_status(db: Session = Depends(get_db)):
    return {"items": EvidenceService.market_data_status(db)}


@router.get("/stocks/{stock_id}")
def get_stock_evidence(stock_id: int, db: Session = Depends(get_db)):
    stock = db.query(StockMaster).filter(StockMaster.stock_id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    return EvidenceService.stock_evidence(db, stock)
