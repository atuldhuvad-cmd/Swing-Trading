from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from sqlalchemy import or_, func

from app.database import get_db
from app.models import StockMaster
from app.schemas.stock import StockCreate, StockUpdate, StockOut
from datetime import datetime

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

@router.post("", response_model=StockOut)
def create_stock(stock_in: StockCreate, db: Session = Depends(get_db)):
    # 1. NSE symbol Canonicalization to uppercase and trim
    stock_in.nse_symbol = stock_in.nse_symbol.strip().upper()
    stock_in.company_name = stock_in.company_name.strip()
    
    # 2. Check duplicate NSE symbol
    existing = db.query(StockMaster).filter(StockMaster.nse_symbol == stock_in.nse_symbol).first()
    if existing:
        raise HTTPException(status_code=409, detail="Stock with this NSE symbol already exists")

    # 3. Check duplicate ISIN if provided
    if stock_in.isin:
        stock_in.isin = stock_in.isin.strip().upper()
        existing_isin = db.query(StockMaster).filter(StockMaster.isin == stock_in.isin).first()
        if existing_isin:
            raise HTTPException(status_code=409, detail="Stock with this ISIN already exists")

    stock = StockMaster(**stock_in.model_dump())
    
    try:
        db.add(stock)
        db.commit()
        db.refresh(stock)
        return stock
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail="Database integrity error")

@router.get("", response_model=List[StockOut])
def get_stocks(
    q: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(StockMaster)
    
    if q:
        search = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(StockMaster.nse_symbol).like(search),
                func.lower(StockMaster.company_name).like(search)
            )
        )
        
    return query.offset(skip).limit(limit).all()

@router.get("/{stock_id}", response_model=StockOut)
def get_stock(stock_id: int, db: Session = Depends(get_db)):
    stock = db.query(StockMaster).filter(StockMaster.stock_id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
    return stock

@router.put("/{stock_id}", response_model=StockOut)
def update_stock(stock_id: int, stock_in: StockUpdate, db: Session = Depends(get_db)):
    stock = db.query(StockMaster).filter(StockMaster.stock_id == stock_id).first()
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")
        
    update_data = stock_in.model_dump(exclude_unset=True)
    
    # Check for ISIN duplication if being updated
    if 'isin' in update_data and update_data['isin']:
        update_data['isin'] = update_data['isin'].strip().upper()
        existing_isin = db.query(StockMaster).filter(
            StockMaster.isin == update_data['isin'],
            StockMaster.stock_id != stock_id
        ).first()
        if existing_isin:
            raise HTTPException(status_code=409, detail="Stock with this ISIN already exists")

    for key, value in update_data.items():
        if key == 'nse_symbol' and value:
             value = value.strip().upper()
        setattr(stock, key, value)
        
    stock.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        db.refresh(stock)
        return stock
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=422, detail="Database integrity error")
