from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

class SourceTypeMasterBase(BaseModel):
    type_name: str = Field(..., max_length=100)
    description: Optional[str] = None

class SourceTypeMasterOut(SourceTypeMasterBase):
    source_type_id: int
    
    model_config = ConfigDict(from_attributes=True)


class SystemSettingBase(BaseModel):
    setting_key: str = Field(..., max_length=100)
    setting_value: str = Field(..., max_length=255)
    description: Optional[str] = None

class SystemSettingOut(SystemSettingBase):
    model_config = ConfigDict(from_attributes=True)

class SystemSettingsUpdate(BaseModel):
    fresh_max_days: int = Field(..., ge=0)
    recent_max_days: int = Field(..., ge=0)
    moderate_max_days: int = Field(..., ge=0)
    stale_max_days: int = Field(..., ge=0)
    universe_max_age_days: int = Field(..., ge=0)
    eligible_normalized_ratings: list[str] = Field(..., min_length=1)

class RatingNormalizationBase(BaseModel):
    original_rating: str = Field(..., max_length=100)
    normalized_rating: str = Field(..., max_length=100)

class RatingNormalizationOut(RatingNormalizationBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)
