from celery import shared_task
import requests
from app.core.db import SessionLocal
from app.models.rss_feed import RSSFeed
from app.models.collection_job import CollectionJob
from app.adapters.rss import RSSAdapter
from app.adapters.registry import ADAPTER_REGISTRY
import json
from datetime import datetime, timezone

# Dead-feed circuit breaker (Fix 1): any feed (RSS/GDELT/HN Algolia -- every
# adapter reachable from fetch_feed_task uses `requests` under the hood, see
# adapters/rss.py, gdelt.py, hn_algolia.py) whose last this-many consecutive
# fetch_feed_task retries-exhausted attempts *all* failed with a
# requests.exceptions.ConnectionError/Timeout gets auto-deactivated, instead
# of retrying a host that's down forever. Deliberately not GDELT-specific --
# tracked per feed_id in Redis, not hardcoded to any one adapter/URL.
FEED_CIRCUIT_BREAKER_THRESHOLD = 5


def _feed_circuit_breaker_key(feed_id) -> str:
    return f"feed:circuit_breaker:consecutive_conn_failures:{feed_id}"


def _get_or_create_source(db, feed: RSSFeed):
    """
    Resolve the `sources` row backing this feed, creating it if needed.
    documents.source_id is an FK to sources.id (not rss_feeds.id) — this is
    the shared find-or-create used by both the async fetch_feed_task path
    and the synchronous aggregation_tasks.py::_stage_collect path.

    Uses INSERT ... ON CONFLICT (url) DO NOTHING + SELECT (same pattern as
    the A3 dedup fix on documents) rather than SELECT-then-INSERT, since two
    pollers can race on the same feed URL — sources.url now has a UNIQUE
    constraint (see FINDINGS.md D4), so a plain SELECT-then-INSERT would
    raise IntegrityError under that race instead of silently creating a
    second row.
    """
    from sqlalchemy.dialects.postgresql import insert
    from app.models.source import Source, SourceCategory

    cat = db.query(SourceCategory).filter(SourceCategory.name == "RSS News").first()
    if not cat:
        cat = SourceCategory(name="RSS News", base_reliability_score=1.0)
        db.add(cat)
        db.commit()
        db.refresh(cat)

    stmt = insert(Source).values(
        category_id=cat.id,
        name=feed.feed_name,
        source_type=feed.source_format,
        url=feed.feed_url,
        schedule_cron="0 * * * *",
        is_active=True,
    ).on_conflict_do_nothing(index_elements=['url'])
    db.execute(stmt)
    db.commit()

    return db.query(Source).filter(Source.url == feed.feed_url).first()


def _record_source_health(db, source_id, success: bool):
    """
    Upsert the source_health row for a source after a poll completes.
    reputation_engine.py (~line 249) reads reliability_penalty as a 0.0-1.0
    fraction subtracted from base_reliability_score (~1.0) then scaled to
    0-100 — see FINDINGS.md D6 for the exact read-side formula this is
    matched against. There is no prior writer to match beyond that formula,
    so consecutive_failures/penalty growth is a new, deliberately simple
    choice: reset to healthy on any success, else penalty grows linearly
    with consecutive_failures capped at 1.0 (fully unreliable at 5+ in a
    row). status is not read anywhere today; kept human-readable for
    dashboards/future use.
    """
    from sqlalchemy.dialects.postgresql import insert
    from app.models.source import SourceHealth

    now = datetime.now(timezone.utc)
    existing = db.query(SourceHealth).filter(SourceHealth.source_id == source_id).first()
    prev_failures = existing.consecutive_failures if existing else 0

    if success:
        values = dict(
            source_id=source_id,
            status="healthy",
            reliability_penalty=0.0,
            consecutive_failures=0,
            last_success_at=now,
        )
    else:
        consecutive_failures = (prev_failures or 0) + 1
        values = dict(
            source_id=source_id,
            status="failing",
            reliability_penalty=min(1.0, consecutive_failures * 0.2),
            consecutive_failures=consecutive_failures,
            last_success_at=existing.last_success_at if existing else None,
        )

    stmt = insert(SourceHealth).values(**values)
    update_cols = {c: stmt.excluded[c] for c in ("status", "reliability_penalty", "consecutive_failures", "last_success_at")}
    stmt = stmt.on_conflict_do_update(index_elements=['source_id'], set_=update_cols)
    db.execute(stmt)
    db.commit()

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
    job_id_pk = None
    try:
        feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
        if not feed:
            return

        # Create Collection Job
        job = CollectionJob(source_id=feed.id, status="created")
        db.add(job)
        db.commit()
        db.refresh(job)
        # Captured as a plain value (not the ORM object) so the exception
        # handler can look this exact job up by primary key, not by
        # "most recent job for this source_id" — two overlapping runs for
        # the same feed (e.g. a manual trigger racing the scheduler) each
        # have their own job, and querying by source_id can mark the wrong
        # one failed (see FINDINGS.md D8).
        job_id_pk = job.job_id

        # Transition to collecting
        job.status = "collecting"
        # Advance last_polled_at as soon as an attempt begins, not only on
        # success (Phase 2 item 8 — was the root cause of the permanent
        # re-fetch loop: schedule_feeds's due-check only looked at
        # last_polled_at, which previously never moved on failure, so a
        # feed that had never/not-recently succeeded looked "due" on every
        # 1-minute Beat tick forever, ignoring poll_interval_minutes
        # entirely). Setting it here, before adapter.fetch() can raise,
        # also closes a second overlap: since it now reflects "an attempt
        # is underway" immediately, schedule_feeds's next tick won't
        # re-dispatch a duplicate attempt for a feed that's still inside
        # fetch_feed_task's own internal 60s/120s/240s retry backoff
        # (item 10) — previously nothing stopped that, since the job row
        # for this source already reads "failed" as soon as the first
        # retry-triggering exception hits (see the except block below),
        # well before the retry chain actually exhausts.
        #
        # A brand-new, never-yet-polled feed is unaffected (item 9): this
        # only fires once an attempt has actually started, so the very
        # first schedule_feeds pass for a feed with last_polled_at=None
        # still dispatches it immediately, same as before.
        feed.last_polled_at = datetime.now(timezone.utc)
        db.commit()

        adapter_cls = ADAPTER_REGISTRY.get(feed.source_format, RSSAdapter)
        adapter = adapter_cls()
        entries = adapter.fetch(feed.feed_url)

        # Fetch succeeded -- this feed's host is reachable, so any
        # in-progress connection/timeout failure streak is over.
        from app.utils.redis_client import redis_client
        redis_client.delete(_feed_circuit_breaker_key(feed.id))

        source = _get_or_create_source(db, feed)
        _record_source_health(db, source.id, success=True)
        client_id = str(feed.client_id) if feed.client_id else None

        from .document_processor import process_document_task

        docs_found = 0
        entries_to_process = []
        new_last_guid = feed.last_entry_guid

        for entry in entries:
            # Check if we already processed this based on guid/published_at.
            # 'id'/'link' cover RSS entries, 'url' covers GDELT, 'objectID' covers HN Algolia.
            guid = entry.get('id') or entry.get('link') or entry.get('url') or entry.get('objectID')
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
                str(source.id),
                raw_payload,
                feed.extract_full_article,
                client_id=client_id,
                source_format=feed.source_format
            )
        
    except Exception as exc:
        db.rollback()
        # Update Job Status if possible — by primary key (job_id_pk), not by
        # "most recent job for this source_id". See FINDINGS.md D8.
        import uuid
        feed_uuid = uuid.UUID(feed_id)
        if job_id_pk is not None:
            job = db.query(CollectionJob).filter(CollectionJob.job_id == job_id_pk).first()
            if job:
                job.status = "failed"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()

        if self.request.retries >= self.max_retries:
            # Retries exhausted. Only record failing health if this feed has
            # a Source row already (i.e. it has succeeded at least once
            # before) — Source rows are lazily created on first successful
            # poll (FINDINGS.md D4), and D6 doesn't pre-create one just to
            # log a health row for a feed that has never worked.
            from app.models.source import Source
            failed_feed = db.query(RSSFeed).filter(RSSFeed.id == feed_uuid).first()
            if failed_feed:
                existing_source = db.query(Source).filter(Source.url == failed_feed.feed_url).first()
                if existing_source:
                    _record_source_health(db, existing_source.id, success=False)

                # Dead-feed circuit breaker: only connection/timeout errors
                # count towards the streak -- an HTTP 4xx/5xx or parse-error
                # exception means the host answered, which is a different
                # failure mode and shouldn't silently deactivate a feed
                # whose remote host is actually up.
                from app.utils.redis_client import redis_client
                import structlog
                breaker_key = _feed_circuit_breaker_key(failed_feed.id)
                if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
                    consecutive = redis_client.incrby(breaker_key)
                    if consecutive >= FEED_CIRCUIT_BREAKER_THRESHOLD:
                        failed_feed.is_active = False
                        db.commit()
                        redis_client.delete(breaker_key)
                        structlog.get_logger().bind(task="fetch_feed_task").warning(
                            "feed_circuit_breaker_tripped_deactivated",
                            feed_id=feed_id,
                            feed_name=failed_feed.feed_name,
                            feed_url=failed_feed.feed_url,
                            consecutive_connection_failures=consecutive,
                            threshold=FEED_CIRCUIT_BREAKER_THRESHOLD,
                            last_error=str(exc),
                        )
                else:
                    # A non-connection/timeout failure breaks the
                    # "consecutive connection/timeout failures" streak.
                    redis_client.delete(breaker_key)

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

            # Note: this branch used to also try releasing a Client pipeline
            # lock keyed `pipeline:running:{client_id}`. Confirmed via repo-wide
            # grep (Phase 1, INFRA_FORENSICS.md) that nothing sets that key
            # anymore — the Phase 13 orchestrator uses `pipeline:lock:{client_id}`
            # exclusively (see PipelineRun watchdog in aggregation_tasks.py,
            # which targets the correct key). Removed as dead code rather than
            # repointed, since CollectionJob and PipelineRun are separate FSMs
            # and this watchdog has no PipelineRun row to correlate against.

    except Exception as exc:
        db.rollback()
        log.error("watchdog_failed", error=str(exc))
    finally:
        db.close()


# Feed revival watchdog: the other half of the dead-feed circuit breaker
# above. FEED_CIRCUIT_BREAKER_THRESHOLD trips a feed to is_active=False, but
# nothing ever flipped it back -- confirmed live (2026-09-02/03): 8 of 9
# GDELT feeds tripped together during a real GDELT-side outage and stayed
# deactivated 17+ hours after the outage should have cleared, with no path
# back except a manual DB write. This task is that path: retry a
# deactivated feed on a cooldown and reactivate it only on a real
# successful fetch.
FEED_REVIVAL_COOLDOWN_MINUTES = 60


@shared_task
def feed_revival_watchdog():
    """
    Retries deactivated (circuit-breaker-tripped) feeds one at a time on a
    cooldown, reactivating on a real successful fetch. Runs hourly.

    Deliberately does a single direct adapter.fetch() per feed, not a call
    into fetch_feed_task -- that task's own 3-attempt exponential-backoff
    retry chain is the right shape for an in-flight scheduled poll, but
    piling several of those chains back-to-back against a host that may
    still be down is exactly what produced the DB-connection pressure spike
    seen tonight during manual verification. One lightweight attempt per
    feed per hour is enough to detect recovery without that cost, and the
    time.sleep pause below (not just relying on Celery's own concurrency)
    keeps even a fast HN/RSS-speed host from being hit with a burst of
    only tens of milliseconds apart.
    """
    import time
    from datetime import timedelta
    from app.utils.redis_client import redis_client
    import structlog

    log = structlog.get_logger().bind(task="feed_revival_watchdog")
    db = SessionLocal()
    try:
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(minutes=FEED_REVIVAL_COOLDOWN_MINUTES)
        candidates = db.query(RSSFeed).filter(
            RSSFeed.is_active == False,  # noqa: E712
            (RSSFeed.last_polled_at == None) | (RSSFeed.last_polled_at < cooldown_cutoff)  # noqa: E711
        ).all()

        if not candidates:
            log.info("revival_no_candidates")
            return

        log.info("revival_candidates_found", total=len(candidates))

        for feed in candidates:
            log.info("revival_attempt_started", feed_id=str(feed.id), name=feed.feed_name, source_format=feed.source_format)
            feed.last_polled_at = datetime.now(timezone.utc)
            db.commit()

            try:
                adapter_cls = ADAPTER_REGISTRY.get(feed.source_format, RSSAdapter)
                adapter = adapter_cls()
                adapter.fetch(feed.feed_url)

                # Real success: reactivate and clear any leftover breaker state.
                feed.is_active = True
                db.commit()
                redis_client.delete(_feed_circuit_breaker_key(feed.id))
                log.warning(
                    "revival_succeeded_feed_reactivated",
                    feed_id=str(feed.id),
                    name=feed.feed_name,
                    feed_url=feed.feed_url,
                )
            except Exception as fetch_exc:
                # Still down -- leave deactivated. last_polled_at was already
                # advanced above, so the cooldown restarts from now.
                log.info(
                    "revival_attempt_failed",
                    feed_id=str(feed.id),
                    name=feed.feed_name,
                    error=str(fetch_exc),
                )

            time.sleep(2)

    except Exception as exc:
        db.rollback()
        log.error("revival_watchdog_failed", error=str(exc))
    finally:
        db.close()
