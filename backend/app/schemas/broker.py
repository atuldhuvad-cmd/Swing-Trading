from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime

class BrokerAliasBase(BaseModel):
    alias_name: str = Field(..., max_length=255)

class BrokerAliasCreate(BrokerAliasBase):
    pass

class BrokerAliasOut(BrokerAliasBase):
    alias_id: int
    broker_id: int
    
    model_config = ConfigDict(from_attributes=True)


class BrokerRelationshipBase(BaseModel):
    predecessor_id: int
    successor_id: int
    relationship_type: str = Field(..., max_length=50)
    effective_date: Optional[datetime] = None
    notes: Optional[str] = None

class BrokerRelationshipCreate(BrokerRelationshipBase):
    pass

class BrokerRelationshipOut(BrokerRelationshipBase):
    relationship_id: int
    
    model_config = ConfigDict(from_attributes=True)


class RecommendationStreamBase(BaseModel):
    stream_name: str = Field(..., max_length=255)
    stream_type: str = Field(..., max_length=100)
    frequency: str = Field(..., max_length=50)
    source_url: Optional[str] = Field(None, max_length=500)
    enabled: bool = True
    notes: Optional[str] = None

class RecommendationStreamCreate(RecommendationStreamBase):
    pass

class RecommendationStreamUpdate(BaseModel):
    stream_name: Optional[str] = Field(None, max_length=255)
    stream_type: Optional[str] = Field(None, max_length=100)
    frequency: Optional[str] = Field(None, max_length=50)
    source_url: Optional[str] = Field(None, max_length=500)
    enabled: Optional[bool] = None
    notes: Optional[str] = None
    last_checked: Optional[datetime] = None
    next_check_due: Optional[datetime] = None
    last_successful_update: Optional[datetime] = None

class RecommendationStreamOut(RecommendationStreamBase):
    stream_id: int
    broker_id: int
    last_checked: Optional[datetime]
    next_check_due: Optional[datetime]
    last_successful_update: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class BrokerBase(BaseModel):
    canonical_name: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=255)
    website: Optional[str] = Field(None, max_length=255)
    active_status: bool = True
    credibility_status: Optional[str] = Field(None, max_length=50)
    is_historical_only: bool = False
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    enabled_for_new_ingestion: bool = True
    notes: Optional[str] = None

class BrokerCreate(BrokerBase):
    pass

class BrokerUpdate(BaseModel):
    canonical_name: Optional[str] = Field(None, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    website: Optional[str] = Field(None, max_length=255)
    active_status: Optional[bool] = None
    credibility_status: Optional[str] = Field(None, max_length=50)
    is_historical_only: Optional[bool] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    enabled_for_new_ingestion: Optional[bool] = None
    notes: Optional[str] = None

class BrokerOut(BrokerBase):
    broker_id: int
    normalized_name: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    aliases: List[BrokerAliasOut] = []
    
    model_config = ConfigDict(from_attributes=True)
