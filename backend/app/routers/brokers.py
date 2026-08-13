from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models import BrokerMaster, BrokerAlias, BrokerRelationship, RecommendationStream
from app.schemas.broker import (
    BrokerCreate, BrokerUpdate, BrokerOut,
    BrokerAliasCreate, BrokerAliasOut,
    BrokerRelationshipCreate, BrokerRelationshipOut,
    RecommendationStreamCreate, RecommendationStreamUpdate, RecommendationStreamOut
)
from app.services.broker_service import BrokerService

router = APIRouter(prefix="/api/brokers", tags=["brokers"])

@router.post("", response_model=BrokerOut)
def create_broker(broker_in: BrokerCreate, db: Session = Depends(get_db)):
    broker_dict = broker_in.model_dump()
    broker_dict['canonical_name'] = broker_dict['canonical_name'].strip()
    broker_dict['display_name'] = broker_dict['display_name'].strip()
    broker_dict['normalized_name'] = broker_dict['canonical_name'].lower().replace(" ", "")
    
    # Check duplicate
    existing = db.query(BrokerMaster).filter(BrokerMaster.normalized_name == broker_dict['normalized_name']).first()
    if existing:
        raise HTTPException(status_code=409, detail="Broker with this name already exists")
        
    broker = BrokerMaster(**broker_dict)
    try:
        db.add(broker)
        db.commit()
        db.refresh(broker)
        return broker
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=422, detail="Database integrity error")

@router.get("", response_model=List[BrokerOut])
def get_brokers(
    q: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    if q:
        brokers = BrokerService.resolve_broker_identity(db, q)
        return brokers[skip:skip+limit]
    
    return db.query(BrokerMaster).offset(skip).limit(limit).all()

@router.get("/{broker_id}", response_model=BrokerOut)
def get_broker(broker_id: int, db: Session = Depends(get_db)):
    broker = db.query(BrokerMaster).filter(BrokerMaster.broker_id == broker_id).first()
    if not broker:
        raise HTTPException(status_code=404, detail="Broker not found")
    return broker

@router.put("/{broker_id}", response_model=BrokerOut)
def update_broker(broker_id: int, broker_in: BrokerUpdate, db: Session = Depends(get_db)):
    broker = db.query(BrokerMaster).filter(BrokerMaster.broker_id == broker_id).first()
    if not broker:
        raise HTTPException(status_code=404, detail="Broker not found")
        
    update_data = broker_in.model_dump(exclude_unset=True)
    if 'canonical_name' in update_data and update_data['canonical_name']:
        update_data['normalized_name'] = update_data['canonical_name'].strip().lower().replace(" ", "")
        existing = db.query(BrokerMaster).filter(
            BrokerMaster.normalized_name == update_data['normalized_name'],
            BrokerMaster.broker_id != broker_id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Broker with this name already exists")
            
    for key, value in update_data.items():
        setattr(broker, key, value)
        
    broker.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        db.refresh(broker)
        return broker
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=422, detail="Database integrity error")

# --- Aliases ---

@router.post("/{broker_id}/aliases", response_model=BrokerAliasOut)
def add_alias(broker_id: int, alias_in: BrokerAliasCreate, db: Session = Depends(get_db)):
    broker = db.query(BrokerMaster).filter(BrokerMaster.broker_id == broker_id).first()
    if not broker:
        raise HTTPException(status_code=404, detail="Broker not found")
        
    existing = db.query(BrokerAlias).filter(BrokerAlias.alias_name == alias_in.alias_name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Alias already exists")
        
    alias = BrokerAlias(broker_id=broker_id, **alias_in.model_dump())
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return alias

@router.get("/{broker_id}/aliases", response_model=List[BrokerAliasOut])
def get_aliases(broker_id: int, db: Session = Depends(get_db)):
    return db.query(BrokerAlias).filter(BrokerAlias.broker_id == broker_id).all()

# --- Relationships ---

@router.post("/{broker_id}/relationships", response_model=BrokerRelationshipOut)
def add_relationship(broker_id: int, rel_in: BrokerRelationshipCreate, db: Session = Depends(get_db)):
    if rel_in.predecessor_id != broker_id and rel_in.successor_id != broker_id:
        raise HTTPException(status_code=422, detail="Broker must be either predecessor or successor")
        
    pred = db.query(BrokerMaster).filter(BrokerMaster.broker_id == rel_in.predecessor_id).first()
    succ = db.query(BrokerMaster).filter(BrokerMaster.broker_id == rel_in.successor_id).first()
    
    if not pred or not succ:
        raise HTTPException(status_code=404, detail="Broker not found")
        
    rel = BrokerRelationship(**rel_in.model_dump())
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel

@router.get("/{broker_id}/relationships")
def get_relationships(broker_id: int, db: Session = Depends(get_db)):
    return BrokerService.get_broker_lineage(db, broker_id)

# --- Streams ---

@router.post("/{broker_id}/streams", response_model=RecommendationStreamOut)
def add_stream(broker_id: int, stream_in: RecommendationStreamCreate, db: Session = Depends(get_db)):
    broker = db.query(BrokerMaster).filter(BrokerMaster.broker_id == broker_id).first()
    if not broker:
        raise HTTPException(status_code=404, detail="Broker not found")
        
    stream = RecommendationStream(broker_id=broker_id, **stream_in.model_dump())
    try:
        db.add(stream)
        db.commit()
        db.refresh(stream)
        return stream
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=422, detail="Invalid stream data (e.g., invalid frequency)")

@router.get("/{broker_id}/streams", response_model=List[RecommendationStreamOut])
def get_streams(broker_id: int, db: Session = Depends(get_db)):
    return db.query(RecommendationStream).filter(RecommendationStream.broker_id == broker_id).all()

@router.put("/{broker_id}/streams/{stream_id}", response_model=RecommendationStreamOut)
def update_stream(broker_id: int, stream_id: int, stream_in: RecommendationStreamUpdate, db: Session = Depends(get_db)):
    stream = db.query(RecommendationStream).filter(
        RecommendationStream.broker_id == broker_id,
        RecommendationStream.stream_id == stream_id
    ).first()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
        
    for key, value in stream_in.model_dump(exclude_unset=True).items():
        setattr(stream, key, value)
        
    stream.updated_at = datetime.utcnow()
    try:
        db.commit()
        db.refresh(stream)
        return stream
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=422, detail="Invalid stream data")
