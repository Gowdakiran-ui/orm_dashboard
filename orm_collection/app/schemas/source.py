from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal

class SourceCategoryBase(BaseModel):
    name: str
    base_reliability_score: Decimal = Decimal('1.00')

class SourceCategoryCreate(SourceCategoryBase):
    pass

class SourceCategoryResponse(SourceCategoryBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class SourceBase(BaseModel):
    name: str
    source_type: str
    url: Optional[str] = None
    schedule_cron: str
    query_template: Optional[str] = None
    is_active: bool = True

class SourceCreate(SourceBase):
    category_id: Optional[UUID] = None

class SourceUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    url: Optional[str] = None
    schedule_cron: Optional[str] = None
    query_template: Optional[str] = None
    is_active: Optional[bool] = None
    category_id: Optional[UUID] = None

class SourceResponse(SourceBase):
    id: UUID
    category_id: Optional[UUID]
    model_config = ConfigDict(from_attributes=True)
