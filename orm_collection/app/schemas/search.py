from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class SearchSourceConfigurationBase(BaseModel):
    source_type: str
    enabled: bool = True
    daily_quota: int = 10000
    rate_limit: int = 60
    reliability_score: float = 1.0
    source_priority: int = 1

class SearchSourceConfigurationCreate(SearchSourceConfigurationBase):
    pass

class SearchSourceConfigurationResponse(SearchSourceConfigurationBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class SearchJobResponse(BaseModel):
    job_id: UUID
    source_type: str
    keyword: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    results_found: int
    results_saved: int
    results_matched: int
    
    model_config = ConfigDict(from_attributes=True)

class SearchStatusResponse(BaseModel):
    status: str
    active_sources: int
    total_search_jobs: int
    total_results_found: int

class SearchTriggerRequest(BaseModel):
    keyword: str
