from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
import time

from app.core.db import get_db
from app.schemas.match import DocumentSimulationRequest, SimulationResponse, MatchResult
from app.services.matching_engine import engine_instance

router = APIRouter()

@router.post("/simulate", response_model=SimulationResponse)
def simulate_document_match(request: DocumentSimulationRequest, db: Session = Depends(get_db)):
    """
    Simulate matching a document against the Global Matching Engine.
    Does NOT save to the database. Useful for testing keywords.
    """
    start_time = time.time()
    
    # If not loaded, force load
    if not engine_instance.is_loaded:
        engine_instance.refresh_processor(db)
        
    raw_matches = engine_instance.find_matches(request.text)
    
    matches = []
    for m in raw_matches:
        matches.append(MatchResult(
            keyword="[Hidden]", # We could return it if we modify flash text payload
            entity_id=m["entity_id"],
            client_id=m["client_id"],
            match_type=m["match_type"],
            match_confidence=m["confidence"],
            category=m["category"]
        ))
        
    processing_time_ms = (time.time() - start_time) * 1000
    
    return SimulationResponse(
        matches=matches,
        processing_time_ms=processing_time_ms,
        total_keywords_loaded=len(engine_instance.processor)
    )

@router.post("/refresh-engine")
def refresh_matching_engine(db: Session = Depends(get_db)):
    count = engine_instance.refresh_processor(db)
    return {"status": "success", "keywords_loaded": count}
