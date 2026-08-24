from celery import shared_task
from app.core.db import SessionLocal
from app.models.entity import EntityKeyword
from app.models.search import SearchSourceConfiguration, SearchCursor, SearchJob
from app.adapters.reddit import RedditAdapter
from app.adapters.youtube import YouTubeAdapter
from app.workers.document_processor import process_document_task
from datetime import datetime, timezone, timedelta
import json

@shared_task(bind=True, max_retries=3)
def schedule_searches(self):
    """
    Celery Beat task to schedule searches based on keyword search_frequency_minutes.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        active_sources = db.query(SearchSourceConfiguration).filter(SearchSourceConfiguration.enabled == True).all()
        active_keywords = db.query(EntityKeyword).filter(EntityKeyword.is_active == True).all()
        
        for source in active_sources:
            for kw in active_keywords:
                # Check when it was last searched
                cursor = db.query(SearchCursor).filter(
                    SearchCursor.keyword_id == kw.id,
                    SearchCursor.source_type == source.source_type
                ).first()
                
                needs_search = False
                if not cursor or not cursor.last_searched_at:
                    needs_search = True
                else:
                    elapsed = (now - cursor.last_searched_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
                    if elapsed >= kw.search_frequency_minutes:
                        needs_search = True
                        
                if needs_search:
                    # Enqueue task
                    execute_search_task.delay(source.source_type, kw.keyword_text, str(kw.id))
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()

@shared_task(bind=True, max_retries=3)
def execute_search_task(self, source_type: str, keyword: str, keyword_id: str):
    db = SessionLocal()
    job = None
    try:
        source_config = db.query(SearchSourceConfiguration).filter(SearchSourceConfiguration.source_type == source_type).first()
        if not source_config or not source_config.enabled:
            return
            
        cursor = db.query(SearchCursor).filter(
            SearchCursor.keyword_id == keyword_id,
            SearchCursor.source_type == source_type
        ).first()
        
        cursor_val = cursor.cursor_value if cursor else None
        
        # Instantiate Adapter
        adapter = None
        if source_type == 'reddit':
            adapter = RedditAdapter()
        elif source_type == 'youtube':
            adapter = YouTubeAdapter()
        else:
            return
            
        # Create Job
        job = SearchJob(source_type=source_type, keyword=keyword, status="processing")
        db.add(job)
        db.commit()
        db.refresh(job)
        
        raw_results, new_cursor_val = adapter.search(keyword, cursor=cursor_val, limit=25)
        
        for res in raw_results:
            normalized_doc = adapter.normalize(res, str(source_config.id))
            raw_payload = json.dumps(res)
            # Enqueue to Document Processor
            # document_processor handles standard normalization mapping
            # Wait, the document_processor expects raw_payload and calls adapter.normalize
            # But process_document_task expects source_id (which here is the SearchSourceConfiguration id or a dummy)
            # We need to adapt `process_document_task` to handle search results, or just use it.
            # But `process_document_task` hardcodes `RSSAdapter()`. We need to fix that or bypass it.
            # Since `process_document_task` hardcoded `RSSAdapter`, we can instead just call `process_and_save_document` directly here 
            # OR pass the adapter type to `process_document_task`.
            
            # Let's call process_and_save_document directly for milestone 4, or ideally we'd pass source_type to document_processor.
            # For simplicity, we just save here as we already normalized it!
            from app.services.document_service import process_and_save_document
            from app.schemas.document import NormalizedDocument
            
            try:
                norm_doc = NormalizedDocument(**normalized_doc)
                is_saved, is_dedup, match_count = process_and_save_document(db, norm_doc)
                if is_saved: job.results_saved += 1
                if match_count > 0: job.results_matched += 1
            except Exception as e:
                import structlog
                import traceback
                logger = structlog.get_logger()
                logger.error(
                    "search_document_processing_failed",
                    task="execute_search_task",
                    document=normalized_doc,
                    url=normalized_doc.get("url"),
                    client="N/A",
                    exception_type=type(e).__name__,
                    stack_trace=traceback.format_exc(),
                    processing_stage="normalization_and_save"
                )
                
        job.results_found = len(raw_results)
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        
        if not cursor:
            cursor = SearchCursor(keyword_id=keyword_id, source_type=source_type)
            db.add(cursor)
            
        cursor.cursor_value = new_cursor_val
        cursor.last_searched_at = datetime.now(timezone.utc)
        
        db.commit()
        
    except Exception as exc:
        db.rollback()
        if self.request.retries >= self.max_retries:
            # Retries exhausted -- write a terminal failure state instead of
            # letting Celery's MaxRetriesExceededError propagate uncaught,
            # which previously left the SearchJob (if one had already been
            # created) orphaned at status="processing" forever (FINAL.md
            # #15; matches the pattern already used correctly in
            # fetch_feed_task/process_document_task). Re-queried by primary
            # key rather than reusing `job` directly, since db.rollback()
            # above may have detached it from the session.
            if job is not None:
                fail_job = db.query(SearchJob).filter(SearchJob.job_id == job.job_id).first()
                if fail_job:
                    fail_job.status = "failed"
                    fail_job.completed_at = datetime.now(timezone.utc)
                    db.commit()
        backoff = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=backoff)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Search job watchdog
# ---------------------------------------------------------------------------

_SEARCH_JOB_TIMEOUT_HOURS = 2


@shared_task
def search_job_watchdog():
    """
    Watchdog for SearchJob.status, mirroring collection_watchdog's
    (collection_tasks.py) staleness-sweep pattern. Runs every 15 minutes.

    Root cause this closes: execute_search_task above creates a SearchJob
    row with status="processing" and commits (models/search.py:35,
    started_at has server_default=func.now(), set automatically at that
    exact moment) before any real work happens. If the worker process dies
    anywhere after that commit (OOM kill, forced restart, an external-API
    hang) the job is stuck in "processing" forever -- the same failure
    class CollectionJob/PipelineRun/Document already hit and got a
    watchdog for; SearchJob never did, until now (FINAL.md #14).

    Threshold: unlike document_processing_watchdog's 10-minute figure
    (derived from a live cold/warm timing measurement), no such measurement
    is possible here -- search_source_configurations and search_jobs both
    have zero rows in this deployment's entire history (search sources have
    never been configured), and no real Reddit/YouTube API credentials
    exist in .env, so there is no live traffic to time and no safe way to
    generate any without making uncontrolled calls to a real external API
    with placeholder credentials. Using collection_watchdog's already-
    established 2-hour timeout instead of inventing an unmeasured number:
    execute_search_task's shape (one external API call, then a loop of
    simple per-item saves via the same process_and_save_document() RSS
    collection uses, all inside a single job row, no multi-stage NLP
    pipeline inline) is structurally the closest analog to CollectionJob in
    this codebase, not to Document's much heavier intelligence-pipeline
    workload. Revisit with real measured data if search sources are ever
    actually configured (see TASK.md/FINDINGS.md).
    """
    from app.models.search import SearchJob
    import structlog

    log = structlog.get_logger().bind(task="search_job_watchdog")
    db = SessionLocal()
    try:
        timeout_limit = datetime.now(timezone.utc) - timedelta(hours=_SEARCH_JOB_TIMEOUT_HOURS)

        stuck_jobs = db.query(SearchJob).filter(
            SearchJob.status == "processing",
            SearchJob.started_at < timeout_limit,
        ).all()

        if not stuck_jobs:
            log.info("watchdog_no_stuck_jobs")
            return

        log.warning("watchdog_found_stuck_jobs", total_stuck=len(stuck_jobs))

        for job in stuck_jobs:
            job_id_str = str(job.job_id)
            log.warning("watchdog_recovering_job", job_id=job_id_str,
                       source_type=job.source_type, keyword=job.keyword,
                       started_at=str(job.started_at))
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

    except Exception as exc:
        db.rollback()
        log.error("watchdog_failed", error=str(exc))
    finally:
        db.close()
