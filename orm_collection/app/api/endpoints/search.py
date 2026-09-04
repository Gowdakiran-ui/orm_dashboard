from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core.db import get_db
from app.models.search import SearchJob, SearchSourceConfiguration
from app.schemas.search import SearchJobResponse, SearchStatusResponse

router = APIRouter()

# POST /{source_type} (trigger_search) removed 2026-09-04 (Run-Pipeline-gated
# architecture, Part F of the forensic audit): it dispatched
# execute_search_task -- which can call the metered YouTube API -- directly,
# with no connection to Run Pipeline, no per-client scoping (a bare
# `keyword: str`, not tied to any tracked entity), and only basic login auth
# (not require_client_access). It was the one remaining path that could
# still incur paid-source cost with zero relation to a client's own trigger,
# the exact thing the redesign exists to prevent. Not wired into the
# frontend UI (confirmed via grep before removal), so nothing in the product
# used it. execute_search_task itself is left defined (not deleted) --
# same pattern as the removed beat-scheduled aggregation tasks -- since
# schedule_searches (also unreachable post-redesign) still references it.

@router.get("/jobs", response_model=List[SearchJobResponse])
def get_search_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(SearchJob).order_by(SearchJob.started_at.desc(), SearchJob.job_id.desc()).offset(skip).limit(limit).all()

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
