from pydantic import BaseModel, ConfigDict
from typing import List
from uuid import UUID
from datetime import datetime

class MatchResult(BaseModel):
    keyword: str
    entity_id: UUID
    client_id: UUID
    match_type: str
    match_confidence: float
    category: str

class DocumentSimulationRequest(BaseModel):
    text: str

class SimulationResponse(BaseModel):
    matches: List[MatchResult]
    processing_time_ms: float
    total_keywords_loaded: int
