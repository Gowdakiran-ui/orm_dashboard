from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.db import get_db
from app.models.search import SearchJob, SearchSourceConfiguration
from app.schemas.search import SearchJobResponse, SearchStatusResponse, SearchTriggerRequest
from app.workers.search_tasks import execute_search_task

router = APIRouter()

@router.post("/{source_type}")
def trigger_search(source_type: str, request: SearchTriggerRequest, db: Session = Depends(get_db)):
    # Validate source_type
    if source_type not in ['reddit', 'youtube']:
        raise HTTPException(status_code=400, detail="Invalid source_type. Must be 'reddit' or 'youtube'")

    source_config = db.query(SearchSourceConfiguration).filter(SearchSourceConfiguration.source_type == source_type).first()
    if not source_config or not source_config.enabled:
        raise HTTPException(status_code=400, detail=f"{source_type} source is not enabled or configured.")

    # We create a dummy keyword_id for manual triggers, or ideally we'd pass an actual one if we're searching an existing entity keyword.
    # For this endpoint, we'll just pass a dummy UUID.
    import uuid
    dummy_keyword_id = str(uuid.uuid4())

    execute_search_task.delay(source_type, request.keyword, dummy_keyword_id)
    return {"status": "queued", "source_type": source_type, "keyword": request.keyword}

@router.get("/jobs", response_model=List[SearchJobResponse])
def get_search_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(SearchJob).order_by(SearchJob.started_at.desc(), SearchJob.id.desc()).offset(skip).limit(limit).all()

@router.get("/status", response_model=SearchStatusResponse)
def get_search_status(db: Session = Depends(get_db)):
    active_sources = db.query(SearchSourceConfiguration).filter(SearchSourceConfiguration.enabled == True).count()
    total_jobs = db.query(SearchJob).count()
    from sqlalchemy.sql import func
    total_results = db.query(func.sum(SearchJob.results_found)).scalar() or 0
    
    return {
        "status": "online",
        "active_sources": active_sources,
        "total_search_jobs": total_jobs,
        "total_results_found": total_results
    }
