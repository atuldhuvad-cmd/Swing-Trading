from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.database import get_db
from app.models import BrokerRecommendation, SourceReference, RecommendationSource, StockMaster, BrokerMaster
from app.schemas.recommendation import (
    BrokerRecommendationCreate, BrokerRecommendationOut, RecommendationDetailOut, SourceReferenceCreate, SourceReferenceOut, RecommendationStatusHistoryOut
)
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

@router.post("", response_model=BrokerRecommendationOut)
def create_recommendation(rec_in: BrokerRecommendationCreate, db: Session = Depends(get_db)):
    # Validate entities exist
    if not db.query(StockMaster).filter(StockMaster.stock_id == rec_in.stock_id).first():
        raise HTTPException(status_code=422, detail="Unknown stock")
    if not db.query(BrokerMaster).filter(BrokerMaster.broker_id == rec_in.broker_id).first():
        raise HTTPException(status_code=422, detail="Unknown broker")
        
    # Date validation
    if rec_in.recommendation_date.replace(tzinfo=None) > __import__('datetime').datetime.utcnow():
        raise HTTPException(status_code=422, detail="Future recommendation date rejected")
        
    # Price validations
    if rec_in.entry_price_low is not None and rec_in.entry_price_high is not None:
        if rec_in.entry_price_low > rec_in.entry_price_high:
            raise HTTPException(status_code=422, detail="Entry low greater than high")
            
    # Source validation
    for ev in rec_in.evidence:
        if ev.verification_status not in ['VERIFIED_PRIMARY', 'VERIFIED_SECONDARY', 'PROVISIONAL', 'REJECTED']:
            raise HTTPException(status_code=422, detail="Invalid verification status")

    return RecommendationService.create_recommendation(db, rec_in)

@router.get("", response_model=List[BrokerRecommendationOut])
def get_recommendations(
    stock_id: Optional[int] = None,
    broker_id: Optional[int] = None,
    lifecycle_status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(BrokerRecommendation)
    
    if stock_id:
        query = query.filter(BrokerRecommendation.stock_id == stock_id)
    if broker_id:
        query = query.filter(BrokerRecommendation.broker_id == broker_id)
    if lifecycle_status:
        query = query.filter(BrokerRecommendation.lifecycle_status == lifecycle_status)
        
    return query.order_by(BrokerRecommendation.recommendation_date.desc()).offset(skip).limit(limit).all()

@router.get("/{rec_id}", response_model=RecommendationDetailOut)
def get_recommendation_detail(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(BrokerRecommendation).filter(BrokerRecommendation.recommendation_id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
        
    sources = db.query(SourceReference).join(RecommendationSource).filter(RecommendationSource.recommendation_id == rec_id).all()
    
    res = RecommendationDetailOut.model_validate(rec)
    res.sources = [SourceReferenceOut.model_validate(s) for s in sources]
    
    from app.models import RecommendationStatusHistory
    history = db.query(RecommendationStatusHistory).filter(RecommendationStatusHistory.recommendation_id == rec_id).all()
    res.status_history = [RecommendationStatusHistoryOut.model_validate(h) for h in history]
    
    return res

@router.post("/{rec_id}/sources", response_model=SourceReferenceOut)
def attach_source(rec_id: int, source_in: SourceReferenceCreate, db: Session = Depends(get_db)):
    rec = db.query(BrokerRecommendation).filter(BrokerRecommendation.recommendation_id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
        
    source = SourceReference(**source_in.model_dump())
    try:
        db.add(source)
        db.flush()
        
        rec_source = RecommendationSource(
            recommendation_id=rec_id,
            source_reference_id=source.source_reference_id
        )
        db.add(rec_source)
        db.commit()
        db.refresh(source)
        return source
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=422, detail="Failed to attach source")

@router.post("/{rec_id}/supersede", response_model=BrokerRecommendationOut)
def supersede_recommendation(rec_id: int, rec_in: BrokerRecommendationCreate, db: Session = Depends(get_db)):
    return RecommendationService.supersede_recommendation(db, rec_id, rec_in)
