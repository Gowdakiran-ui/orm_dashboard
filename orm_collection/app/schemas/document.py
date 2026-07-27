from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

class DocumentMatchResponse(BaseModel):
    id: UUID
    matched_entity_id: UUID
    match_type: str
    match_confidence: float
    matched_text: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class DocumentBase(BaseModel):
    url: str
    source_id: Optional[UUID] = None
    document_type: str
    title: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    language: str = "en"

class DocumentResponse(DocumentBase):
    id: UUID
    content_hash: str
    collected_at: datetime
    matches: List[DocumentMatchResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

class NormalizedDocument(BaseModel):
    source_id: UUID
    source_type: str
    title: str
    content: str
    url: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    collected_at: datetime
    raw_payload: str # JSON encoded string of the raw data
