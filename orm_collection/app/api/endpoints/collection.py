from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from uuid import UUID
import datetime

from app.core.db import get_db
from app.core.rate_limit import limiter, STRICT_RATE_LIMIT
from app.core.auth import get_current_user, require_client_access, user_has_client_access
from app.core.celery_app import celery_app
from app.models.rss_feed import RSSFeed
from app.models.collection_job import CollectionJob
from app.models.user import User
from app.workers.collection_tasks import fetch_feed_task

router = APIRouter()

@router.post("/trigger/{feed_id}")
@limiter.limit(STRICT_RATE_LIMIT)
def trigger_collection(
    request: Request,
    response: Response,
    feed_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    if not user_has_client_access(db, current_user.id, feed.client_id):
        raise HTTPException(status_code=403, detail="Not authorized for this client")

    # Use send_task to explicitly target the configured celery_app (Redis)
    # instead of relying on @shared_task's thread-local app binding, which
    # falls back to the bare default app (-> connection refused) when
    # invoked from FastAPI's sync-endpoint threadpool. Same fix already
    # verified for run_client_pipeline in clients.py.
    celery_app.send_task("app.workers.collection_tasks.fetch_feed_task", args=[str(feed.id)])
    return {"status": "queued", "feed_id": feed.id}

@router.get("/status")
def get_status(
    client_id: UUID,
    db: Session = Depends(get_db),
    _access: UUID = Depends(require_client_access),
):
    # Tenant-isolation fix: this used to aggregate across every client's
    # feeds/documents/jobs with no filtering at all -- any authenticated
    # user polling their own dashboard saw platform-wide counts move
    # whenever ANY other client's collection/pipeline ran (confirmed via
    # fetchCommandCenterStats in api.ts, which already took a clientId
    # param but never sent it). Filtered the same way telemetry.py's
    # per-client aggregate already does: Document via
    # DocumentMatch->Entity.client_id, RSSFeed/CollectionJob via
    # RSSFeed.client_id (topical_global feeds have no owning client and
    # are intentionally excluded from a per-client view).
    active_feeds = db.query(RSSFeed).filter(
        RSSFeed.is_active == True, RSSFeed.client_id == client_id
    ).count()

    from app.models.document import Document, DocumentMatch
    from app.models.entity import Entity
    client_docs = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Entity.client_id == client_id
    ).distinct()
    total_docs = client_docs.count()
    total_matches = db.query(DocumentMatch).join(Entity).filter(
        Entity.client_id == client_id
    ).count()

    # Calculate docs collected in last 24h
    now = datetime.datetime.now(datetime.timezone.utc)
    last_24h = now - datetime.timedelta(days=1)
    docs_today = client_docs.filter(Document.collected_at >= last_24h).count()

    # Collection job success/failure summary
    client_jobs = db.query(CollectionJob).join(RSSFeed).filter(RSSFeed.client_id == client_id)
    total_jobs  = client_jobs.count()
    failed_jobs = client_jobs.filter(CollectionJob.status == "failed").count()
    success_jobs = client_jobs.filter(CollectionJob.status == "completed").count()
    
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
def get_collection_errors(
    client_id: UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
    _access: UUID = Depends(require_client_access),
):
    """
    Centralized error tracking endpoint.
    Returns the most recent failed collection jobs with full metadata,
    scoped to the caller's client.
    """
    failed = (
        db.query(CollectionJob)
        .join(RSSFeed, RSSFeed.id == CollectionJob.source_id)
        .filter(CollectionJob.status == "failed", RSSFeed.client_id == client_id)
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
