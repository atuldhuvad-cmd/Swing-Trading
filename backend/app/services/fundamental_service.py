from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ..models import FundamentalSnapshot, FundamentalMetric, StockMaster
from decimal import Decimal

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
        source_reference_id: int = None,
        reference_date: date = None
    ) -> FundamentalSnapshot:
        if metrics is None:
            metrics = {}
            
        if entity_type not in ['ORDINARY', 'BANK', 'NBFC']:
            raise ValueError(f"Invalid entity_type: {entity_type}")
            
        # check if a previous snapshot exists for the SAME stock, financial period, and period type
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
        ref_date = reference_date or datetime.utcnow().date()
        
        for m_name, m_data in metrics.items():
            status = m_data.get('status', 'UNKNOWN')
            val = m_data.get('value', None)
            
            if status not in ['KNOWN', 'UNKNOWN', 'NOT_APPLICABLE', 'STALE', 'UNSUPPORTED']:
                raise ValueError(f"Invalid status: {status}")
                
            if status in ['UNKNOWN', 'NOT_APPLICABLE', 'UNSUPPORTED', 'STALE']:
                val = None
                
            if status == 'KNOWN' and (ref_date - as_of_date).days > cls.STALENESS_THRESHOLD_DAYS:
                status = 'STALE'
                val = None
                
            if val is not None:
                val = Decimal(str(val))
                
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
