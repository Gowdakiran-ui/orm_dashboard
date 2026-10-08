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

    # Brand co-occurrence containment (contamination_bug_sweep.md,
    # 2026-09-13): raw DocumentMatch->Entity.client_id count with no
    # entity_type filter or brand-co-occurrence check at all -- same gap
    # documents.py's get_client_visible_documents (_brand_gated_document_ids)
    # already closes on the client-facing document feed. Require the
    # client's own brand/product entity to also have a match on the same
    # document before it counts toward this client's raw totals. A client
    # with no brand/product entity configured at all is an existing-data
    # edge case -- logged and left ungated, same as documents.py, rather
    # than silently zeroing out these counts for such a client.
    brand_or_product_ids = [
        r[0] for r in db.query(Entity.id).filter(
            Entity.client_id == client_id, Entity.entity_type.in_(("brand", "product"))
        ).all()
    ]
    brand_doc_ids = None
    if brand_or_product_ids:
        brand_doc_ids = {
            r[0] for r in db.query(DocumentMatch.document_id).filter(
                DocumentMatch.matched_entity_id.in_(brand_or_product_ids)
            ).all()
        }

    client_docs = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Entity.client_id == client_id
    ).distinct()
    total_matches_query = db.query(DocumentMatch).join(Entity).filter(
        Entity.client_id == client_id
    )
    if brand_doc_ids is not None:
        client_docs = client_docs.filter(Document.id.in_(brand_doc_ids))
        total_matches_query = total_matches_query.filter(DocumentMatch.document_id.in_(brand_doc_ids))
    total_docs = client_docs.count()
    total_matches = total_matches_query.count()

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
