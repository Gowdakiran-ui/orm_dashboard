"""
Celery entry points for the one-time historical backfill. Never called by Run
Pipeline and not in any beat schedule: they run only when enqueued explicitly
(the CLI, or the one-time enqueue at client onboarding).

run_client_backfill - processes a bounded number of slices, then re-enqueues
    itself (a continuation of the same one-time job, capped by MAX_RESUMES)
    while PENDING slices remain. A YouTube budget pause waits for the next
    Pacific-time quota reset.
drain_backfill_nlp  - feeds backfilled documents to the NLP queue in small
    batches, in priority order, up to BACKFILL_MAX_PROCESS_DOCS_PER_CLIENT per
    client, only while that queue is short, so live pipeline runs are never
    queued behind a backfill. Exactly one drain chain runs at a time.

Collect-only flag (app.services.backfill.control): while set, nothing is handed to NLP.

Both honour the Redis stop switch (app.services.backfill.control): setting it
stops all backfill work within one slice / one drain tick.
"""
import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import structlog
from celery import shared_task

from app.core.db import SessionLocal

logger = structlog.get_logger()

NLP_QUEUE_MAX = 30          # defer draining while nlp_queue already holds more than this
NLP_BATCH = 20              # documents handed to the NLP queue per drain tick (per client)
DRAIN_INTERVAL_SECONDS = 60
DRAIN_MAX_TICKS = 5000
DRAIN_CHAIN_KEY = "backfill:drain:chain"
DRAIN_CHAIN_TTL = 300       # a live chain refreshes this every tick; a dead one frees the slot in 5 minutes
MAX_RESUMES = 30
LOCK_TTL_SECONDS = 3600


def _seconds_until_youtube_reset() -> int:
    """YouTube quota resets at midnight Pacific Time."""
    now = dt.datetime.now(ZoneInfo("America/Los_Angeles"))
    nxt = (now + dt.timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max(60, int((nxt - now).total_seconds()))


def _send(name: str, **kwargs):
    # send_task by name on the project's own app (a bare shared_task.apply_async outside a worker
    # falls back to Celery's default AMQP app), same convention as the rest of the API
    from app.core.celery_app import celery_app
    return celery_app.send_task(name, **kwargs)


def start_drain() -> bool:
    """Start the NLP feeder unless a chain is already alive. Returns True when a new chain was started."""
    from app.services.backfill import control
    from app.utils.redis_client import redis_client
    if control.is_collect_only():
        return False
    chain = uuid.uuid4().hex
    if not redis_client.client.set(DRAIN_CHAIN_KEY, chain, nx=True, ex=DRAIN_CHAIN_TTL):
        return False
    _send("app.workers.backfill_tasks.drain_backfill_nlp", kwargs={"tick": 0, "chain": chain}, countdown=5)
    return True


@shared_task(bind=True, queue="io_queue", max_retries=0)
def run_client_backfill(self, client_id: str, config: dict = None, resume_count: int = 0):
    from app.services.backfill import control
    from app.services.backfill.engine import BackfillConfig, run_client
    from app.utils.redis_client import redis_client

    if control.is_stopped():
        logger.info("backfill_stopped_by_switch", client_id=client_id)
        return {"status": "stopped"}

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

    # hand new documents to NLP at a controlled rate (one chain only)
    start_drain()

    if summary.get("stopped"):
        return summary
    if summary["remaining"] > 0 and resume_count < MAX_RESUMES and (summary["processed"] > 0 or summary.get("paused")):
        delay = _seconds_until_youtube_reset() if summary.get("paused") and summary["processed"] == 0 else 10
        _send("app.workers.backfill_tasks.run_client_backfill", args=[client_id, config, resume_count + 1], countdown=delay)
        summary["resumed_in_seconds"] = delay
    return summary


@shared_task(bind=True, queue="io_queue", max_retries=0)
def drain_backfill_nlp(self, tick: int = 0, chain: str = None):
    from app.services.backfill import control, processing
    from app.utils.redis_client import redis_client

    if control.is_stopped():
        redis_client.delete(DRAIN_CHAIN_KEY)
        return {"status": "stopped", "tick": tick}

    if control.is_collect_only():
        redis_client.delete(DRAIN_CHAIN_KEY)
        return {"status": "collect_only", "tick": tick}

    chain = chain or uuid.uuid4().hex
    owner = redis_client.get(DRAIN_CHAIN_KEY)
    if owner and owner != chain:
        return {"status": "superseded", "tick": tick}      # another chain owns the feeder: this one ends here
    redis_client.client.set(DRAIN_CHAIN_KEY, chain, ex=DRAIN_CHAIN_TTL)

    db = SessionLocal()
    dispatched = 0
    deferred = False
    waiting = 0
    try:
        try:
            deferred = int(redis_client.client.llen("nlp_queue")) > NLP_QUEUE_MAX
        except Exception:
            deferred = False   # cannot read the queue length: still go slowly (one small batch)

        for cid in processing.clients_with_pending(db):
            res = processing.dispatch(db, cid, 0 if deferred else NLP_BATCH)
            dispatched += res["dispatched"]
            waiting += res["pending_left"] if res["cap_remaining"] > 0 else 0   # only counts clients still under their cap
    finally:
        db.close()

    # keep going only while there is capped-in work left to hand over (or the queue was merely busy)
    if (waiting > 0 or (deferred and waiting > 0)) and tick < DRAIN_MAX_TICKS:
        _send("app.workers.backfill_tasks.drain_backfill_nlp", kwargs={"tick": tick + 1, "chain": chain},
              countdown=DRAIN_INTERVAL_SECONDS)
        return {"status": "deferred" if deferred else "dispatched", "dispatched": dispatched, "tick": tick}
    redis_client.delete(DRAIN_CHAIN_KEY)
    return {"status": "idle", "dispatched": dispatched, "tick": tick}
