"""
celery_app.py — Phase 13

Pipeline execution order in beat_schedule:
    Collection          → schedule-feeds-every-minute (io_queue)
    Search              → schedule-searches-every-minute (io_queue)
    [Entity Matching    → triggered per-document via document_processor task]
    [Topic/Sentiment    → triggered per-document via intelligence_tasks]
    Trend Detection     → calculate-trends-every-hour (aggregation_queue)  ← R1
    Risk                → (triggered per-document via calculate_document_risk)
    Alert               → evaluate-alerts-every-hour (aggregation_queue)
    Narrative           → calculate-narratives-every-hour (aggregation_queue)
    Reputation          → calculate-reputation-every-2-hours (aggregation_queue)

R1: calculate_client_trends is now registered in beat_schedule,
    running every hour to aggregate trends after sentiment has been processed
    for documents collected in the rolling 24-hour window.
"""
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "orm_collection",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'app.workers.collection_tasks',
        'app.workers.document_processor',
        'app.workers.search_tasks',
        'app.workers.intelligence_tasks',
        'app.workers.aggregation_tasks',   # R1: explicitly included for beat
        'app.workers.backup_tasks',
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        # I/O-bound tasks
        'app.workers.collection_tasks.fetch_feed_task':   {'queue': 'io_queue'},
        'app.workers.collection_tasks.schedule_feeds':    {'queue': 'io_queue'},
        'app.workers.collection_tasks.flush_metrics_task':{'queue': 'io_queue'},
        'app.workers.collection_tasks.collection_watchdog':{'queue': 'io_queue'},
        'app.workers.aggregation_tasks.pipeline_run_watchdog':{'queue': 'io_queue'},
        'app.workers.intelligence_tasks.document_processing_watchdog':{'queue': 'io_queue'},
        'app.workers.search_tasks.execute_search_task':   {'queue': 'io_queue'},
        'app.workers.search_tasks.schedule_searches':     {'queue': 'io_queue'},
        'app.workers.search_tasks.search_job_watchdog':   {'queue': 'io_queue'},
        # Backups (Section 10) -- lightweight periodic I/O work, same
        # category as the watchdogs above, not worth a dedicated queue.
        'app.workers.backup_tasks.run_backup':            {'queue': 'io_queue'},
        # CPU-bound NLP tasks
        'app.workers.document_processor.process_document_task': {'queue': 'cpu_queue'},
        'app.workers.intelligence_tasks.process_document_intelligence': {'queue': 'nlp_queue'},
        # Aggregation tasks (all on aggregation_queue)
        'app.workers.aggregation_tasks.calculate_client_trends':      {'queue': 'aggregation_queue'},
        'app.workers.aggregation_tasks.calculate_client_risks':       {'queue': 'aggregation_queue'},
        'app.workers.aggregation_tasks.calculate_document_risk':      {'queue': 'aggregation_queue'},
        'app.workers.aggregation_tasks.evaluate_alerts':              {'queue': 'aggregation_queue'},
        'app.workers.aggregation_tasks.calculate_narratives':         {'queue': 'aggregation_queue'},
        'app.workers.aggregation_tasks.calculate_reputation_score':   {'queue': 'aggregation_queue'},
        'app.workers.aggregation_tasks.calculate_executive_reputation': {'queue': 'aggregation_queue'},
        'app.workers.aggregation_tasks.calculate_competitor_benchmarks': {'queue': 'aggregation_queue'},
        # Phase 13: Manual pipeline runs on isolated pipeline_queue
        # This keeps scheduler tasks and manual runs from competing for the same workers
        'app.workers.aggregation_tasks.run_client_pipeline': {'queue': 'pipeline_queue'},
    },
    beat_schedule={
        # --- Collection Layer ---
        'schedule-feeds-every-minute': {
            'task': 'app.workers.collection_tasks.schedule_feeds',
            'schedule': crontab(minute='*'),
        },
        'schedule-searches-every-minute': {
            'task': 'app.workers.search_tasks.schedule_searches',
            'schedule': crontab(minute='*'),
        },
        'flush-metrics-every-5-minutes': {
            'task': 'app.workers.collection_tasks.flush_metrics_task',
            'schedule': crontab(minute='*/5'),
        },
        # D7: collection_watchdog exists (recovers CollectionJobs stuck in
        # collecting/processing past a 2h timeout) but was never scheduled —
        # see FINDINGS.md D7. Two jobs were found stuck live (20+ and 3+
        # days old) before this was added.
        'collection-watchdog-every-15-minutes': {
            'task': 'app.workers.collection_tasks.collection_watchdog',
            'schedule': crontab(minute='*/15'),
        },

        # Phase 1: PipelineRun (Phase 13) had no watchdog at all — the reason
        # 12 rows sat non-terminal for up to 21 days (INFRA_FORENSICS.md
        # Symptom #1/#2, reconciled in this same phase). Routed to io_queue,
        # not pipeline_queue, so it still runs even if the pipeline_queue
        # worker itself is the one that died.
        'pipeline-run-watchdog-every-15-minutes': {
            'task': 'app.workers.aggregation_tasks.pipeline_run_watchdog',
            'schedule': crontab(minute='*/15'),
        },

        # Document.processing_status had the same stuck-forever failure mode
        # as CollectionJob and PipelineRun above, just never got a watchdog.
        # Found live: 130 documents stuck up to 11+ days. Routed to io_queue,
        # not nlp_queue, so it still runs even if the nlp_queue worker itself
        # is the one that died -- same reasoning as pipeline_run_watchdog.
        'document-processing-watchdog-every-15-minutes': {
            'task': 'app.workers.intelligence_tasks.document_processing_watchdog',
            'schedule': crontab(minute='*/15'),
        },

        # SearchJob.status had the same stuck-forever failure mode as
        # CollectionJob/PipelineRun/Document above, just never got a
        # watchdog (FINAL.md #14). Routed to io_queue, same reasoning as
        # the other three watchdogs.
        'search-job-watchdog-every-15-minutes': {
            'task': 'app.workers.search_tasks.search_job_watchdog',
            'schedule': crontab(minute='*/15'),
        },

        # --- R1: Trend Detection — runs every hour ---
        # Scheduled AFTER entity matching and sentiment analysis which are
        # triggered per-document via intelligence_tasks (process_document_intelligence).
        # Documents collected in the 24h window are available by the time
        # this hourly aggregation runs.
        'calculate-trends-every-hour': {
            'task': 'app.workers.aggregation_tasks.calculate_client_trends',
            'schedule': crontab(minute='0', hour='*'),  # top of every hour
        },

        # --- Risk Engine — runs every hour (3 min after trends) ---
        # Aggregates risk scores for all clients once new trends and sentiments are available.
        'calculate-risks-every-hour': {
            'task': 'app.workers.aggregation_tasks.calculate_client_risks',
            'schedule': crontab(minute='3', hour='*'),
        },

        # --- Alert Engine — runs every hour (5 min after trends) ---
        # Alert evaluation reads from trend_events written by calculate_client_trends.
        # 5-minute offset gives trends time to commit before alerts are evaluated.
        'evaluate-alerts-every-hour': {
            'task': 'app.workers.aggregation_tasks.evaluate_alerts',
            'schedule': crontab(minute='5', hour='*'),
        },

        # --- Narrative Engine — runs every hour (10 min after trends) ---
        'calculate-narratives-every-hour': {
            'task': 'app.workers.aggregation_tasks.calculate_narratives',
            'schedule': crontab(minute='10', hour='*'),
        },

        # --- Reputation Engine — runs every 2 hours ---
        # Reputation is a higher-order aggregation; less frequent is sufficient.
        'calculate-reputation-every-2-hours': {
            'task': 'app.workers.aggregation_tasks.calculate_reputation_score',
            'schedule': crontab(minute='15', hour='*/2'),
        },

        # --- Executive Reputation — runs every 2 hours ---
        'calculate-executive-reputation-every-2-hours': {
            'task': 'app.workers.aggregation_tasks.calculate_executive_reputation',
            'schedule': crontab(minute='20', hour='*/2'),
        },

        # --- Competitor Benchmarks — runs every 4 hours ---
        'calculate-benchmarks-every-4-hours': {
            'task': 'app.workers.aggregation_tasks.calculate_competitor_benchmarks',
            'schedule': crontab(minute='30', hour='*/4'),
        },

        # --- Database Backup (Section 10) — runs daily at 02:00 UTC ---
        # Off-peak relative to the hourly/every-2h/every-4h aggregation jobs
        # above. See app/workers/backup_tasks.py and docs/BACKUP.md.
        'run-backup-daily': {
            'task': 'app.workers.backup_tasks.run_backup',
            'schedule': crontab(minute='0', hour='2'),
        },
    }
)


from celery.signals import worker_process_init, task_failure, task_success
import structlog

logger = structlog.get_logger()


def _incr_task_counter(prefix: str, task_name: str) -> None:
    """Best-effort Redis INCR backing the /metrics celery_task_{failed,success}_total
    gauges (API_FORENSICS.md Section 3, app/core/metrics.py). Metrics must
    never break task completion handling, so a Redis hiccup here is
    swallowed, not raised.
    """
    try:
        from app.utils.redis_client import redis_client
        redis_client.incrby(f"metrics:celery:{prefix}:{task_name}")
    except Exception as e:
        logger.warning("celery_metrics_incr_failed", prefix=prefix, task_name=task_name, error=str(e))


@task_failure.connect
def handle_task_failure(
    sender=None, task_id=None, exception=None,
    args=None, kwargs=None, traceback=None, einfo=None, **other
):
    task_name = sender.name if sender else "Unknown"
    logger.error(
        "celery_task_failed",
        task_id=task_id,
        task_name=task_name,
        exception=str(exception),
        args=args,
        kwargs=kwargs
    )
    _incr_task_counter("failed", task_name)


@task_success.connect
def handle_task_success(sender=None, result=None, **other):
    _incr_task_counter("success", sender.name if sender else "Unknown")


@worker_process_init.connect
def init_celery_worker(**kwargs):
    import os

    # CELERY_SKIP_MATCHING_ENGINE is no longer set anywhere (removed from
    # celery-worker-io in docker-compose.yml). It was based on the false
    # premise that io_queue tasks never touch engine_instance --
    # pipeline_stage_collect (aggregation_tasks.py) is routed to io_queue
    # and calls process_and_save_document -> engine_instance.process_document.
    # Skipping this init left that worker's engine frozen at whatever
    # keywords existed at container startup, since it also skipped
    # start_pubsub_listener() below -- confirmed live to silently produce
    # zero DocumentMatch rows for any client onboarded afterward. Kept as a
    # manual escape hatch (env var, not deleted) rather than removed, in
    # case a future worker split reintroduces a queue that genuinely never
    # touches the matching engine.
    if os.environ.get("CELERY_SKIP_MATCHING_ENGINE", "false").lower() == "true":
        return

    from app.core.db import SessionLocal
    from app.services.matching_engine import engine_instance
    from app.core.pubsub import start_pubsub_listener

    # Phase 5 item 25: same unguarded-DB-access issue as main.py's lifespan()
    # — an OperationalError here previously killed the worker process before
    # it could pick up a single task. Log and continue degraded instead;
    # refresh_processor's other callers repopulate the engine once the DB
    # recovers.
    db = SessionLocal()
    try:
        engine_instance.refresh_processor(db)
    except Exception as e:
        logger.error("Failed to load matching engine at worker startup; continuing degraded", error=str(e))
    finally:
        db.close()

    start_pubsub_listener()
