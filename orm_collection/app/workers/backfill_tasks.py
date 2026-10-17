"""
Celery entry points for the one-time historical backfill. Never called by Run
Pipeline and not in any beat schedule: they run only when enqueued explicitly
(scripts/run_backfill.py, or the one-time enqueue at client onboarding).

run_client_backfill - processes a bounded number of slices, then re-enqueues
    itself (a continuation of the same one-time job, capped by max_resumes)
    while PENDING slices remain. A YouTube budget pause waits for the next
    Pacific-time quota reset.
drain_backfill_nlp  - feeds backfilled documents to the NLP queue in small
    batches, only while that queue is short, so live pipeline runs are never
    queued behind a backfill.
"""
import datetime as dt
from zoneinfo import ZoneInfo

import structlog
from celery import shared_task

from app.core.db import SessionLocal

logger = structlog.get_logger()

NLP_QUEUE_MAX = 30          # defer draining while nlp_queue already holds more than this
NLP_BATCH = 20              # documents handed to the NLP queue per drain tick
DRAIN_INTERVAL_SECONDS = 60
DRAIN_MAX_TICKS = 5000
MAX_RESUMES = 30
LOCK_TTL_SECONDS = 3600


def _seconds_until_youtube_reset() -> int:
    """YouTube quota resets at midnight Pacific Time."""
    now = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    nxt = (now + dt.timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max(60, int((nxt - now).total_seconds()))


@shared_task(bind=True, queue="io_queue", max_retries=0)
def run_client_backfill(self, client_id: str, config: dict = None, resume_count: int = 0):
    from app.services.backfill.engine import BackfillConfig, run_client
    from app.utils.redis_client import redis_client

    lock_key = f"backfill:lock:{client_id}"
    if not redis_client.client.set(lock_key, self.request.id or "1", nx=True, ex=LOCK_TTL_SECONDS):
        logger.info("backfill_already_running", client_id=client_id)
        return {"status": "already_running"}
    db = SessionLocal()
    try:
        cfg = BackfillConfig.from_dict(config)
        summary = run_client(db, client_id, cfg)
        logger.info("backfill_run_complete", client_id=client_id, resume_count=resume_count, **{
            k: v for k, v in summary.items() if k not in ("unavailable",)})
    finally:
        db.close()
        redis_client.delete(lock_key)

    # hand new documents to NLP at a controlled rate
    drain_backfill_nlp.apply_async(kwargs={"tick": 0}, countdown=DRAIN_INTERVAL_SECONDS)

    if summary["remaining"] > 0 and resume_count < MAX_RESUMES and (summary["processed"] > 0 or summary.get("paused")):
        delay = _seconds_until_youtube_reset() if summary.get("paused") and summary["processed"] == 0 else 10
        run_client_backfill.apply_async(args=[client_id, config, resume_count + 1], countdown=delay)
        summary["resumed_in_seconds"] = delay
    return summary


@shared_task(bind=True, queue="io_queue", max_retries=0)
def drain_backfill_nlp(self, tick: int = 0):
    from app.models.document import Document
    from app.models.source import Source
    from app.utils.redis_client import redis_client

    db = SessionLocal()
    try:
        pending = db.query(Document.id, Source.url).join(Source, Source.id == Document.source_id).filter(
            Source.url.like("backfill://%"), Document.processing_status == "PENDING",
        ).order_by(Document.published_at.desc()).limit(NLP_BATCH).all()
        if not pending:
            return {"status": "idle", "tick": tick}

        deferred = False
        try:
            deferred = int(redis_client.client.llen("nlp_queue")) > NLP_QUEUE_MAX
        except Exception:
            deferred = False   # cannot read the queue length: still go slowly (one small batch)

        dispatched = 0
        if not deferred:
            from app.workers.intelligence_tasks import process_document_intelligence
            now = dt.datetime.now(dt.timezone.utc)
            for doc_id, url in pending:
                client_id = url.split("/")[2] if url.count("/") >= 3 else None
                db.query(Document).filter(Document.id == doc_id).update(
                    {"processing_status": "PROCESSING", "processing_started_at": now}, synchronize_session=False)
                dispatched += 1
            db.commit()
            for doc_id, url in pending:
                client_id = url.split("/")[2] if url.count("/") >= 3 else None
                process_document_intelligence.apply_async(args=[str(doc_id), client_id], queue="nlp_queue")
    finally:
        db.close()

    if tick < DRAIN_MAX_TICKS:
        drain_backfill_nlp.apply_async(kwargs={"tick": tick + 1}, countdown=DRAIN_INTERVAL_SECONDS)
    return {"status": "deferred" if deferred else "dispatched", "dispatched": dispatched, "tick": tick}
