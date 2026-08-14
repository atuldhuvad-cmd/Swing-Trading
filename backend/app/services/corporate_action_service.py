from sqlalchemy.orm import Session
from datetime import date
from decimal import Decimal
from typing import List, Optional, Dict, Any

from app.models import CorporateAction, DailyOhlcv

class CorporateActionService:
    @staticmethod
    def store_action(db: Session, stock_id: int, action_type: str, ex_date: date, 
                     ratio_numerator: Optional[Decimal] = None, ratio_denominator: Optional[Decimal] = None, 
                     cash_amount: Optional[Decimal] = None, source_name: str = 'SYSTEM', 
                     source_reference: Optional[str] = None, notes: Optional[str] = None) -> CorporateAction:
        if action_type in ('SPLIT', 'BONUS'):
            if ratio_numerator is None or ratio_denominator is None:
                raise ValueError("Ratio is required for SPLIT/BONUS")
            if ratio_numerator <= 0 or ratio_denominator <= 0:
                raise ValueError("Ratio must be positive")
                
        action = CorporateAction(
            stock_id=stock_id,
            action_type=action_type,
            ex_date=ex_date,
            ratio_numerator=ratio_numerator,
            ratio_denominator=ratio_denominator,
            cash_amount=cash_amount,
            source_name=source_name,
            source_reference=source_reference,
            notes=notes
        )
        db.add(action)
        db.commit()
        db.refresh(action)
        return action

    @staticmethod
    def get_actions(db: Session, stock_id: int, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[CorporateAction]:
        query = db.query(CorporateAction).filter(CorporateAction.stock_id == stock_id)
        if start_date:
            query = query.filter(CorporateAction.ex_date >= start_date)
        if end_date:
            query = query.filter(CorporateAction.ex_date <= end_date)
        return query.order_by(CorporateAction.ex_date.desc()).all()

    @staticmethod
    def get_adjustment_factors(actions: List[CorporateAction], target_date: date) -> Dict[str, Decimal]:
        price_factor = Decimal('1.0')
        volume_factor = Decimal('1.0')
        
        for act in sorted(actions, key=lambda x: x.ex_date, reverse=True):
            if act.ex_date <= target_date:
                continue
            
            if act.action_type == 'SPLIT':
                price_factor *= (act.ratio_denominator / act.ratio_numerator)
                volume_factor *= (act.ratio_numerator / act.ratio_denominator)
            elif act.action_type == 'BONUS':
                existing = act.ratio_denominator
                bonus = act.ratio_numerator
                total = existing + bonus
                price_factor *= (existing / total)
                volume_factor *= (total / existing)
                
        return {'price_factor': price_factor, 'volume_factor': volume_factor}

    @staticmethod
    def apply_adjustments(db: Session, stock_id: int, raw_ohlcv_list: List[DailyOhlcv]) -> List[Dict[str, Any]]:
        actions = CorporateActionService.get_actions(db, stock_id)
        
        adjusted_data = []
        for ohlcv in raw_ohlcv_list:
            dt = ohlcv.trading_date.date()
            factors = CorporateActionService.get_adjustment_factors(actions, dt)
            
            p_f = float(factors['price_factor'])
            v_f = float(factors['volume_factor'])
            
            adjusted_data.append({
                'trading_date': ohlcv.trading_date,
                'series': ohlcv.series,
                'open': ohlcv.open * p_f,
                'high': ohlcv.high * p_f,
                'low': ohlcv.low * p_f,
                'close': ohlcv.close * p_f,
                'volume': int(ohlcv.volume * v_f),
                'original': ohlcv
            })
            
        return adjusted_data
