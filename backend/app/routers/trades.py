from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.schemas.trade import TradeJournalCreate, TradeJournalUpdate, TradeJournalOut, PositionSizeRequest, PositionSizeResponse
from app.services.trade_service import TradeService

router = APIRouter(prefix='/api/trades', tags=['Trades'])

@router.post('/position-size', response_model=PositionSizeResponse)
def calculate_position_size(req: PositionSizeRequest):
    return TradeService.calculate_position_size(req)

@router.post('/', response_model=TradeJournalOut)
def create_trade(trade_in: TradeJournalCreate, db: Session = Depends(get_db)):
    try:
        return TradeService.create_trade(db, trade_in)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

@router.get('/', response_model=List[TradeJournalOut])
def list_trades(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return TradeService.get_trades(db, skip=skip, limit=limit)

@router.get('/{trade_id}', response_model=TradeJournalOut)
def get_trade(trade_id: int, db: Session = Depends(get_db)):
    trade = TradeService.get_trade(db, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail='Trade not found')
    return trade

@router.patch('/{trade_id}', response_model=TradeJournalOut)
def update_trade(trade_id: int, trade_in: TradeJournalUpdate, db: Session = Depends(get_db)):
    try:
        trade = TradeService.update_trade(db, trade_id, trade_in)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not trade:
        raise HTTPException(status_code=404, detail='Trade not found')
    return trade
