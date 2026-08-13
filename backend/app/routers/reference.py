from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import SourceTypeMaster, SystemSetting, RatingNormalization
from app.schemas.system import SourceTypeMasterOut, SystemSettingOut, RatingNormalizationOut

router = APIRouter(prefix="/api/reference", tags=["reference"])

@router.get("/source-types", response_model=List[SourceTypeMasterOut])
def get_source_types(db: Session = Depends(get_db)):
    return db.query(SourceTypeMaster).all()

@router.get("/settings", response_model=List[SystemSettingOut])
def get_settings(db: Session = Depends(get_db)):
    return db.query(SystemSetting).all()

@router.get("/ratings", response_model=List[RatingNormalizationOut])
def get_ratings(db: Session = Depends(get_db)):
    return db.query(RatingNormalization).all()
