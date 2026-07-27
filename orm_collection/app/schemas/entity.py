from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum

class KeywordCategory(str, Enum):
    PRIMARY = "PRIMARY"
    ALIAS = "ALIAS"
    EXECUTIVE = "EXECUTIVE"
    PRODUCT = "PRODUCT"
    COMPETITOR = "COMPETITOR"
    RISK = "RISK"

class EntityAliasBase(BaseModel):
    alias_text: str

class EntityAliasCreate(EntityAliasBase):
    pass

class EntityAliasResponse(EntityAliasBase):
    id: UUID
    entity_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class EntityKeywordBase(BaseModel):
    keyword_text: str
    match_type: str = "exact"
    category: KeywordCategory = KeywordCategory.PRIMARY
    priority: int = 1
    is_active: bool = True

class EntityKeywordCreate(EntityKeywordBase):
    pass

class EntityKeywordResponse(EntityKeywordBase):
    id: UUID
    entity_id: UUID
    model_config = ConfigDict(from_attributes=True)

class EntityBase(BaseModel):
    name: str
    entity_type: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    ticker_symbol: Optional[str] = None
    industry: Optional[str] = None

class EntityCreate(EntityBase):
    client_id: UUID

class EntityUpdate(BaseModel):
    name: Optional[str] = None
    entity_type: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    ticker_symbol: Optional[str] = None
    industry: Optional[str] = None

class EntityResponse(EntityBase):
    id: UUID
    client_id: UUID
    created_at: datetime
    aliases: List[EntityAliasResponse] = []
    keywords: List[EntityKeywordResponse] = []
    
    model_config = ConfigDict(from_attributes=True)
