from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import SourceTypeMaster, SystemSetting, RatingNormalization
from app.schemas.system import SourceTypeMasterOut, SystemSettingOut, RatingNormalizationOut, SystemSettingsUpdate

router = APIRouter(prefix="/api/reference", tags=["reference"])

@router.get("/source-types", response_model=List[SourceTypeMasterOut])
def get_source_types(db: Session = Depends(get_db)):
    return db.query(SourceTypeMaster).all()

@router.get("/settings", response_model=List[SystemSettingOut])
def get_settings(db: Session = Depends(get_db)):
    return db.query(SystemSetting).all()

@router.put("/settings", response_model=List[SystemSettingOut])
def update_settings(payload: SystemSettingsUpdate, db: Session = Depends(get_db)):
    thresholds = [payload.fresh_max_days, payload.recent_max_days, payload.moderate_max_days, payload.stale_max_days]
    if thresholds != sorted(thresholds) or len(set(thresholds)) != len(thresholds):
        raise HTTPException(422, "Freshness thresholds must be strictly increasing")
    if payload.universe_max_age_days > payload.stale_max_days:
        raise HTTPException(422, "Universe maximum age cannot exceed the STALE threshold")
    if not all(r.strip() and r.strip().upper() == r.strip() for r in payload.eligible_normalized_ratings):
        raise HTTPException(422, "Eligible ratings must be non-empty normalized uppercase values")
    values = {
        'FRESH_MAX_DAYS': str(payload.fresh_max_days), 'RECENT_MAX_DAYS': str(payload.recent_max_days),
        'MODERATE_MAX_DAYS': str(payload.moderate_max_days), 'STALE_MAX_DAYS': str(payload.stale_max_days),
        'UNIVERSE_MAX_AGE_DAYS': str(payload.universe_max_age_days),
        'ELIGIBLE_BULLISH_RATINGS': ','.join(dict.fromkeys(r.strip() for r in payload.eligible_normalized_ratings)),
    }
    for key, value in values.items():
        row = db.query(SystemSetting).filter(SystemSetting.setting_key == key).first()
        if row:
            row.setting_value = value
        else:
            db.add(SystemSetting(setting_key=key, setting_value=value))
    db.commit()
    return db.query(SystemSetting).order_by(SystemSetting.setting_key).all()

@router.get("/ratings", response_model=List[RatingNormalizationOut])
def get_ratings(db: Session = Depends(get_db)):
    return db.query(RatingNormalization).all()
