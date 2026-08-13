from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.schemas.consensus import StockConsensusOut, CandidateListResponse
from app.services.consensus_service import ConsensusService

router = APIRouter(prefix="/api/consensus", tags=["consensus"])

@router.get("/candidates", response_model=CandidateListResponse)
def get_candidate_universe(
    min_brokers: int = Query(1, ge=0),
    min_upside: Optional[float] = Query(None),
    min_bullish_pct: Optional[float] = Query(None),
    max_age_days: Optional[int] = Query(None),
    verification_status: str = Query('ALL'),
    eligible_ratings: Optional[List[str]] = Query(None),
    sort_by: str = Query('broker_count'),
    sort_order: str = Query('desc'),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    return ConsensusService.get_candidate_universe(
        db=db,
        min_brokers=min_brokers,
        min_upside=min_upside,
        min_bullish_pct=min_bullish_pct,
        max_age_days=max_age_days,
        verification_status=verification_status,
        eligible_ratings=eligible_ratings,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit
    )

@router.get("/stocks/{stock_id}", response_model=StockConsensusOut)
def get_stock_consensus(
    stock_id: int,
    verification_status: str = Query('ALL'),
    eligible_ratings: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    consensus = ConsensusService.calculate_stock_consensus(
        db=db,
        stock_id=stock_id,
        verification_status=verification_status,
        eligible_ratings=eligible_ratings
    )
    if not consensus:
        raise HTTPException(status_code=404, detail="Stock not found")
    return consensus
