from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID

class CollectionJobBase(BaseModel):
    source_id: UUID
    status: str

class CollectionJobResponse(CollectionJobBase):
    job_id: UUID
    started_at: datetime
    completed_at: Optional[datetime] = None
    documents_found: int
    documents_saved: int
    documents_matched: int
    documents_deduplicated: int
    documents_failed: int
    
    model_config = ConfigDict(from_attributes=True)

class SystemStatusResponse(BaseModel):
    status: str
    active_feeds: int
    total_documents_collected: int
    total_documents_matched: int
