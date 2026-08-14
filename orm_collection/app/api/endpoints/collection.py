from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
import datetime

from app.core.db import get_db
from app.models.rss_feed import RSSFeed
from app.models.collection_job import CollectionJob
from app.workers.collection_tasks import fetch_feed_task

router = APIRouter()

@router.post("/trigger/{feed_id}")
def trigger_collection(feed_id: UUID, db: Session = Depends(get_db)):
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
        
    fetch_feed_task.delay(str(feed.id))
    return {"status": "queued", "feed_id": feed.id}

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    active_feeds = db.query(RSSFeed).filter(RSSFeed.is_active == True).count()
    from app.models.document import Document, DocumentMatch
    total_docs = db.query(Document).count()
    total_matches = db.query(DocumentMatch).count()
    
    # Calculate docs collected in last 24h
    now = datetime.datetime.now(datetime.timezone.utc)
    last_24h = now - datetime.timedelta(days=1)
    docs_today = db.query(Document).filter(Document.collected_at >= last_24h).count()
    
    # Collection job success/failure summary
    total_jobs  = db.query(CollectionJob).count()
    failed_jobs = db.query(CollectionJob).filter(CollectionJob.status == "failed").count()
    success_jobs = db.query(CollectionJob).filter(CollectionJob.status == "completed").count()
    
    return {
        "status": "online",
        "active_feeds": active_feeds,
        "total_documents_collected": total_docs,
        "total_documents_matched": total_matches,
        "docs_today": docs_today,
        "rss_active": active_feeds,
        "reddit_collected": 0,
        "yt_collected": 0,
        "queue_health": "100%" if total_jobs == 0 or failed_jobs == 0 else f"{round((success_jobs/total_jobs)*100)}%",
        "platform_health": "Healthy" if failed_jobs == 0 else "Degraded",
        "collection_jobs": {
            "total": total_jobs,
            "completed": success_jobs,
            "failed": failed_jobs
        }
    }

@router.get("/errors")
def get_collection_errors(limit: int = 50, db: Session = Depends(get_db)):
    """
    Centralized error tracking endpoint.
    Returns the most recent failed collection jobs with full metadata.
    """
    failed = (
        db.query(CollectionJob)
        .filter(CollectionJob.status == "failed")
        .order_by(CollectionJob.started_at.desc(), CollectionJob.job_id.desc())
        .limit(limit)
        .all()
    )
    
    if not failed:
        return {"error_count": 0, "errors": [], "message": "No collection errors recorded."}

    feed_ids = list({job.source_id for job in failed if job.source_id})
    feeds = db.query(RSSFeed).filter(RSSFeed.id.in_(feed_ids)).all() if feed_ids else []
    feed_map = {feed.id: feed for feed in feeds}

    errors = []
    for job in failed:
        feed = feed_map.get(job.source_id)
        errors.append({
            "job_id": str(job.job_id),
            "feed_id": str(job.source_id),
            "feed_name": feed.feed_name if feed else "Unknown",
            "feed_url": feed.feed_url if feed else "Unknown",
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "failed_at": job.completed_at.isoformat() if job.completed_at else None,
            "documents_found": job.documents_found,
            "documents_failed": job.documents_failed,
        })

    return {"error_count": len(errors), "errors": errors}
