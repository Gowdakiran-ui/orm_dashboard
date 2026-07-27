from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID

class RSSFeedBase(BaseModel):
    feed_name: str
    feed_url: str
    category: Optional[str] = None
    poll_interval_minutes: int = 60
    is_active: bool = True
    extract_full_article: bool = False

class RSSFeedCreate(RSSFeedBase):
    pass

class RSSFeedUpdate(BaseModel):
    feed_name: Optional[str] = None
    feed_url: Optional[str] = None
    category: Optional[str] = None
    poll_interval_minutes: Optional[int] = None
    is_active: Optional[bool] = None
    extract_full_article: Optional[bool] = None

class RSSFeedResponse(RSSFeedBase):
    id: UUID
    last_polled_at: Optional[datetime] = None
    last_entry_guid: Optional[str] = None
    last_entry_published_at: Optional[datetime] = None
    reliability_score: float
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
