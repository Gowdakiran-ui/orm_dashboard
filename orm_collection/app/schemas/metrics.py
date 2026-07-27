from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID

class MatchingMetricsBase(BaseModel):
    documents_processed: int
    matches_found: int
    processing_time: float
    keywords_loaded: int

class MatchingMetricsResponse(MatchingMetricsBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
