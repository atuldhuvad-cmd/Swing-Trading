from pydantic import BaseModel, model_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

class PositionSizeRequest(BaseModel):
    entry_price: Decimal
    stop_price: Decimal
    max_risk_amount: Decimal
    max_capital_allocation: Optional[Decimal] = None

class PositionSizeResponse(BaseModel):
    status: str
    quantity: Optional[int] = None
    per_share_risk: Optional[Decimal] = None
    total_capital: Optional[Decimal] = None
    reason: Optional[str] = None

class TradeJournalCreate(BaseModel):
    stock_id: int
    candidate_evaluation_id: Optional[int] = None
    risk_reward_result_id: Optional[int] = None
    status: str = 'PLANNED'
    side: str = 'LONG'

    @model_validator(mode='before')
    @classmethod
    def validate_side(cls, values):
        if values.get('side', 'LONG') != 'LONG':
            raise ValueError('Only LONG side is currently supported for personal swing trading')
        return values
        
    planned_entry_price: Optional[Decimal] = None
    planned_stop_price: Optional[Decimal] = None
    planned_target_price: Optional[Decimal] = None
    quantity: Optional[int] = None
    entry_price: Optional[Decimal] = None
    entry_date: Optional[datetime] = None
    entry_note: Optional[str] = None
    entry_price_source: Optional[str] = None
    trade_notes: Optional[str] = None

class TradeJournalUpdate(BaseModel):
    status: Optional[str] = None
    quantity: Optional[int] = None
    entry_price: Optional[Decimal] = None
    entry_date: Optional[datetime] = None
    entry_note: Optional[str] = None
    entry_price_source: Optional[str] = None
    exit_price: Optional[Decimal] = None
    exit_date: Optional[datetime] = None
    exit_note: Optional[str] = None
    exit_price_source: Optional[str] = None
    manual_charges: Optional[Decimal] = None
    trade_notes: Optional[str] = None

class TradeJournalOut(BaseModel):
    trade_id: int
    stock_id: int
    candidate_evaluation_id: Optional[int] = None
    risk_reward_result_id: Optional[int] = None
    status: str
    side: str
    planned_entry_price: Optional[Decimal] = None
    planned_stop_price: Optional[Decimal] = None
    planned_target_price: Optional[Decimal] = None
    quantity: Optional[int] = None
    entry_price: Optional[Decimal] = None
    entry_date: Optional[datetime] = None
    entry_note: Optional[str] = None
    entry_price_source: Optional[str] = None
    exit_price: Optional[Decimal] = None
    exit_date: Optional[datetime] = None
    exit_note: Optional[str] = None
    exit_price_source: Optional[str] = None
    manual_charges: Optional[Decimal] = None
    gross_pnl: Optional[Decimal] = None
    net_pnl: Optional[Decimal] = None
    trade_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
