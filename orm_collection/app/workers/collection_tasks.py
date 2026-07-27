from celery import shared_task
from app.core.db import SessionLocal
from app.models.rss_feed import RSSFeed
from app.models.collection_job import CollectionJob
from app.adapters.rss import RSSAdapter
import json
from datetime import datetime, timezone

@shared_task
def schedule_feeds():
    """
    Celery Beat task to find active feeds that need polling
    and enqueue a fetch_feed_task for each, with concurrency lock,
    due checks, active job checks, and batch scheduling countdowns.
    """
    from app.utils.redis_client import redis_client
    import structlog

    log = structlog.get_logger().bind(task="schedule_feeds")
    
    try:
        redis_client.ping()
    except Exception as e:
        log.critical("redis_unavailable_lock_hardening_aborted", error=str(e))
        return

    scheduler_lock_key = "lock:scheduler:schedule_feeds"

    # Acquire lock to prevent overlapping scheduler cycles
    is_acquired = redis_client.set(scheduler_lock_key, "running", nx=True, ex=600)
    if not is_acquired:
        log.warning("scheduler_already_running_skipping_cycle")
        return

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        feeds = db.query(RSSFeed).filter(RSSFeed.is_active == True).all()
        
        feeds_to_poll = []
        for feed in feeds:
            # 1. Polling interval check
            if feed.last_polled_at:
                diff_minutes = (now - feed.last_polled_at).total_seconds() / 60.0
                if diff_minutes < feed.poll_interval_minutes:
                    log.debug("feed_skip_not_due", feed_id=str(feed.id), name=feed.feed_name, next_poll_in_min=round(feed.poll_interval_minutes - diff_minutes, 1))
                    continue

            # 2. Skip active jobs check
            active_job = db.query(CollectionJob).filter(
                CollectionJob.source_id == feed.id,
                CollectionJob.status.in_(["created", "collecting", "processing"])
            ).first()
            if active_job:
                log.warning("feed_skip_active_job_exists", feed_id=str(feed.id), name=feed.feed_name, job_id=str(active_job.job_id))
                continue

            feeds_to_poll.append(feed)

        if not feeds_to_poll:
            log.info("scheduler_no_feeds_due")
            return

        log.info("scheduler_feeds_due", total_due=len(feeds_to_poll))

        # 3. Batch scheduling with delay spreads
        batch_size = 5
        delay_interval = 10  # seconds between batches
        for idx, feed in enumerate(feeds_to_poll):
            batch_idx = idx // batch_size
            countdown = batch_idx * delay_interval
            fetch_feed_task.apply_async(args=[str(feed.id)], countdown=countdown)
            log.info("feed_scheduled", feed_id=str(feed.id), name=feed.feed_name, countdown=countdown)

    finally:
        redis_client.delete(scheduler_lock_key)
        db.close()

@shared_task(bind=True, max_retries=3)
def fetch_feed_task(self, feed_id: str):
    """
    Fetches an RSS feed and enqueues document processing.
    """
    db = SessionLocal()
    try:
        feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
        if not feed:
            return

        # Create Collection Job
        job = CollectionJob(source_id=feed.id, status="created")
        db.add(job)
        db.commit()
        db.refresh(job)

        # Transition to collecting
        job.status = "collecting"
        db.commit()

        adapter = RSSAdapter()
        entries = adapter.fetch(feed.feed_url)
        
        # Identify the client_id for this feed by name match
        from app.models.client import Client
        clients = db.query(Client).all()
        client = next((c for c in clients if c.name.lower() in feed.feed_name.lower()), None)
        client_id = str(client.id) if client else None

        from .document_processor import process_document_task
        
        docs_found = 0
        entries_to_process = []
        new_last_guid = feed.last_entry_guid
        
        for entry in entries:
            # Check if we already processed this based on guid/published_at
            guid = entry.get('id', entry.get('link'))
            if feed.last_entry_guid == guid:
                break # Reached the last fetched item (assuming chronological order)
                
            docs_found += 1
            if docs_found == 1:
                new_last_guid = guid # Highest in the list
            entries_to_process.append(entry)
            
        feed.last_polled_at = datetime.now(timezone.utc)
        feed.last_entry_guid = new_last_guid
        job.documents_found = docs_found
        
        if docs_found == 0:
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
        else:
            job.status = "processing"
            from app.utils.redis_client import redis_client
            redis_client.set(f"pipeline:job:total:{job.job_id}", docs_found, ex=86400)
            redis_client.set(f"pipeline:job:processed:{job.job_id}", 0, ex=86400)
            
        db.commit()

        # Now dispatch the documents to Document Processor
        for entry in entries_to_process:
            raw_payload = json.dumps(entry)
            process_document_task.delay(
                str(job.job_id), 
                str(feed.id),
                raw_payload, 
                feed.extract_full_article,
                client_id=client_id
            )
        
    except Exception as exc:
        db.rollback()
        # Update Job Status if possible
        import uuid
        feed_uuid = uuid.UUID(feed_id)
        job = db.query(CollectionJob).filter(CollectionJob.source_id == feed_uuid).order_by(CollectionJob.started_at.desc()).first()
        if job:
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        # Exponential backoff: 60s, 120s, 240s
        backoff = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=backoff)
    finally:
        db.close()

import structlog
logger = structlog.get_logger()

@shared_task
def flush_metrics_task():
    """
    Flushes metrics from Redis to PostgreSQL every 5 minutes.
    """
    db = SessionLocal()
    from app.utils.redis_client import redis_client
    from app.models.metrics import MatchingMetrics
    
    try:
        pipeline = redis_client.pipeline()
        pipeline.getset('metrics:documents_processed', 0)
        pipeline.getset('metrics:matches_found', 0)
        pipeline.getset('metrics:processing_time_total', 0.0)
        pipeline.get('metrics:keywords_loaded')
        
        results = pipeline.execute()
        docs = int(results[0] or 0)
        matches = int(results[1] or 0)
        proc_time = float(results[2] or 0.0)
        kws = int(results[3] or 0)
        
        if docs > 0:
            avg_time = proc_time / docs if docs > 0 else 0
            metric = MatchingMetrics(
                documents_processed=docs,
                matches_found=matches,
                processing_time=avg_time,
                keywords_loaded=kws
            )
            db.add(metric)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error("metrics_flush_failed", error=str(e))
    finally:
        db.close()


def check_and_update_job_status(db, job_id: str):
    from app.utils.redis_client import redis_client
    from app.models.collection_job import CollectionJob
    from datetime import datetime, timezone
    
    total_key = f"pipeline:job:total:{job_id}"
    processed_key = f"pipeline:job:processed:{job_id}"
    
    total_raw = redis_client.get(total_key)
    if not total_raw:
        return
        
    total = int(total_raw)
    processed = int(redis_client.get(processed_key) or 0)
    
    if processed >= total:
        job = db.query(CollectionJob).filter(CollectionJob.job_id == job_id).first()
        if job and job.status not in ("completed", "failed"):
            if job.documents_failed > 0:
                job.status = "failed"
            else:
                job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            
            # Clean up Redis keys
            redis_client.delete(total_key)
            redis_client.delete(processed_key)


@shared_task
def collection_watchdog():
    """
    Watchdog task to automatically recover stuck or abandoned CollectionJobs.
    Runs every 15 minutes.
    """
    from datetime import datetime, timezone, timedelta
    from app.utils.redis_client import redis_client
    from app.models.collection_job import CollectionJob
    from app.models.rss_feed import RSSFeed
    from app.models.client import Client
    import structlog

    log = structlog.get_logger().bind(task="collection_watchdog")
    db = SessionLocal()
    try:
        # Configurable timeout: default 2 hours
        timeout_limit = datetime.now(timezone.utc) - timedelta(hours=2)
        
        stuck_jobs = db.query(CollectionJob).filter(
            CollectionJob.status.in_(["collecting", "processing"]),
            CollectionJob.started_at < timeout_limit
        ).all()

        if not stuck_jobs:
            log.info("watchdog_no_stuck_jobs")
            return

        log.warning("watchdog_found_stuck_jobs", total_stuck=len(stuck_jobs))

        for job in stuck_jobs:
            job_id_str = str(job.job_id)
            log.warning("watchdog_recovering_job", job_id=job_id_str, status=job.status, started_at=str(job.started_at))
            
            # Transition status
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            # Record failed count to account for uncompleted documents
            uncompleted_docs = job.documents_found - job.documents_saved - job.documents_deduplicated - job.documents_failed
            if uncompleted_docs > 0:
                job.documents_failed += uncompleted_docs
            db.commit()

            # Clean up Redis keys
            redis_client.delete(f"pipeline:job:total:{job_id_str}")
            redis_client.delete(f"pipeline:job:processed:{job_id_str}")

            # Safely release corresponding Client pipeline locks
            feed = db.query(RSSFeed).filter(RSSFeed.id == job.source_id).first()
            if feed:
                clients = db.query(Client).all()
                client = next((c for c in clients if c.name.lower() in feed.feed_name.lower()), None)
                if client:
                    client_id_str = str(client.id)
                    lock_key = f"pipeline:running:{client_id_str}"
                    current_lock = redis_client.get(lock_key)
                    current_lock_str = current_lock.decode('utf-8') if isinstance(current_lock, bytes) else str(current_lock) if current_lock else None
                    
                    # Verify lock ownership: if lock starts with scheduled- or sync- or is success/failed, we can clear it.
                    # Do not release if it belongs to an active, non-timeout manual Celery task
                    if current_lock_str:
                        if current_lock_str.startswith("scheduled-") or current_lock_str.startswith("sync-") or current_lock_str in ("success", "failed"):
                            redis_client.set(lock_key, "failed", ex=300)
                            log.warning("watchdog_released_client_lock", client_id=client_id_str, lock_key=lock_key, previous_lock=current_lock_str)

    except Exception as exc:
        db.rollback()
        log.error("watchdog_failed", error=str(exc))
    finally:
        db.close()
