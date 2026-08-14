from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.database import get_db
from app.models import StockMaster, CandidateEvaluationRun, RiskRewardResult, FundamentalSnapshot, FundamentalMetric

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

@router.get("/{stock_id}")
def get_stock_evidence(stock_id: int, db: Session = Depends(get_db)):
    stock = db.query(StockMaster).filter(StockMaster.stock_id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
        
    run = db.query(CandidateEvaluationRun).filter(
        CandidateEvaluationRun.stock_id == stock_id
    ).order_by(CandidateEvaluationRun.evaluation_date.desc()).first()
    
    rr_res = None
    if run:
        rr_res = db.query(RiskRewardResult).filter(RiskRewardResult.evaluation_id == run.evaluation_id).first()
        
    snapshot = db.query(FundamentalSnapshot).filter(
        FundamentalSnapshot.stock_id == stock_id,
        FundamentalSnapshot.is_superseded == False
    ).order_by(FundamentalSnapshot.as_of_date.desc()).first()
    
    metrics = []
    if snapshot:
        metrics = db.query(FundamentalMetric).filter(
            FundamentalMetric.snapshot_id == snapshot.snapshot_id
        ).all()
        
    return {
        "stock": {
            "id": stock.stock_id,
            "nse_symbol": stock.nse_symbol,
            "company_name": stock.company_name
        },
        "candidate_run": {
            "evaluation_id": run.evaluation_id if run else None,
            "classification": run.classification if run else None,
            "evaluation_date": run.evaluation_date if run else None
        },
        "risk_reward": {
            "risk_reward_ratio": rr_res.risk_reward_ratio if rr_res else None,
            "support": rr_res.support if rr_res else None,
            "resistance": rr_res.resistance if rr_res else None,
            "target": rr_res.target if rr_res else None,
            "stop_loss": rr_res.stop_loss if rr_res else None
        } if rr_res else None,
        "fundamentals": [
            {
                "metric_name": m.metric_name,
                "metric_value": m.metric_value,
                "status": m.status
            } for m in metrics
        ]
    }
