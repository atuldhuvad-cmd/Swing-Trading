from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ..models import FundamentalSnapshot, FundamentalMetric, StockMaster

class FundamentalService:
    STALENESS_THRESHOLD_DAYS = 90
    
    @classmethod
    def create_snapshot(
        cls, 
        db: Session, 
        stock_id: int, 
        as_of_date: date, 
        financial_period: str, 
        period_type: str, 
        entity_type: str = 'ORDINARY',
        metrics: Dict[str, Dict[str, Any]] = None,
        source_reference_id: int = None
    ) -> FundamentalSnapshot:
        if metrics is None:
            metrics = {}
            
        # check if a previous snapshot exists for the same financial period
        prev = db.query(FundamentalSnapshot).filter(
            FundamentalSnapshot.stock_id == stock_id,
            FundamentalSnapshot.financial_period == financial_period,
            FundamentalSnapshot.period_type == period_type,
            FundamentalSnapshot.is_superseded == False
        ).order_by(desc(FundamentalSnapshot.version)).first()
        
        version = 1
        if prev:
            prev.is_superseded = True
            version = prev.version + 1
            
        snapshot = FundamentalSnapshot(
            stock_id=stock_id,
            as_of_date=as_of_date,
            financial_period=financial_period,
            period_type=period_type,
            source_reference_id=source_reference_id,
            captured_at=datetime.utcnow(),
            version=version,
            is_superseded=False,
            entity_type=entity_type
        )
        db.add(snapshot)
        db.flush()
        
        if prev:
            prev.superseded_by_id = snapshot.snapshot_id
            
        metric_objs = []
        for m_name, m_data in metrics.items():
            status = m_data.get('status', 'UNKNOWN')
            val = m_data.get('value', None)
            
            # Check staleness based on as_of_date vs captured_at, or if data itself is old.
            # But the requirement says "determine staleness deterministically from configured rules"
            if status == 'KNOWN' and (datetime.utcnow().date() - as_of_date).days > cls.STALENESS_THRESHOLD_DAYS:
                status = 'STALE'
                
            metric_objs.append(FundamentalMetric(
                snapshot_id=snapshot.snapshot_id,
                metric_name=m_name,
                metric_value=val,
                status=status
            ))
            
        if metric_objs:
            db.add_all(metric_objs)
            
        return snapshot

    @classmethod
    def get_latest_snapshot(cls, db: Session, stock_id: int) -> Optional[FundamentalSnapshot]:
        return db.query(FundamentalSnapshot).filter(
            FundamentalSnapshot.stock_id == stock_id,
            FundamentalSnapshot.is_superseded == False
        ).order_by(desc(FundamentalSnapshot.as_of_date), desc(FundamentalSnapshot.captured_at)).first()
        
    @classmethod
    def get_historical_snapshots(cls, db: Session, stock_id: int) -> List[FundamentalSnapshot]:
        return db.query(FundamentalSnapshot).filter(
            FundamentalSnapshot.stock_id == stock_id
        ).order_by(desc(FundamentalSnapshot.as_of_date), desc(FundamentalSnapshot.version)).all()

    @classmethod
    def get_metric_evidence(cls, db: Session, snapshot_id: int) -> Dict[str, Dict[str, Any]]:
        metrics = db.query(FundamentalMetric).filter(FundamentalMetric.snapshot_id == snapshot_id).all()
        return {
            m.metric_name: {
                "value": m.metric_value,
                "status": m.status
            }
            for m in metrics
        }
