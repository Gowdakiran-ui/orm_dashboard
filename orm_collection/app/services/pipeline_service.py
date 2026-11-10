"""Starting a client's intelligence pipeline run. One function used by BOTH the web endpoint (POST /clients/{id}/pipeline/run) and the
admin CLI (scripts/run_pipeline.py), so they create identical QUEUED runs.

Behaviour is the endpoint's original sequence (client exists -> reject a duplicate active run for the client -> create the PipelineRun row ->
dispatch run_client_pipeline), plus ONE guard (2026-10-03, decision D4): while any run is active, a new run for a DIFFERENT client is
refused. Why: the database allows 22 client connections and one run peaks at about 15 (audit/connections-assessment.md); two overlapping
runs were never measured and could cross the pause line. MAX_CONCURRENT_PIPELINE_RUNS (default 1) is the number of runs allowed at once.

"Active" = any status that is not terminal (this includes AWAITING_PROCESSING, which the old endpoint's list missed). A run older than the
watchdog timeout is treated as stuck and does not block anything (the watchdog marks it FAILED on its next sweep)."""
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.client import Client
from app.models.pipeline_run import PipelineRun, _TERMINAL_STATES

logger = structlog.get_logger()

# Same value as aggregation_tasks._PIPELINE_RUN_TIMEOUT_MINUTES (pipeline_run_watchdog); a test pins them equal.
PIPELINE_RUN_STALE_MINUTES = 300

CONCURRENCY_MESSAGE = "Another client's pipeline is running. Try again when it finishes."
_ADVISORY_LOCK_KEY = 7240103   # serialises check-then-insert across processes on Postgres


class PipelineStartError(Exception):
    """A refusal the caller maps to an HTTP status (endpoint) or an exit code (CLI)."""

    def __init__(self, status_code: int, detail: str, retry_after_s: Optional[int] = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.retry_after_s = retry_after_s      # set on the 429 run-limit refusal: seconds until the next allowed run


def _stale_cutoff(db: Session) -> datetime:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=PIPELINE_RUN_STALE_MINUTES)
    # SQLite (tests) stores naive datetimes; Postgres compares timezone-aware ones.
    return cutoff.replace(tzinfo=None) if db.get_bind().dialect.name == "sqlite" else cutoff


def active_runs(db: Session):
    """Non-terminal, not-stuck runs, newest first."""
    return (
        db.query(PipelineRun)
        .filter(~PipelineRun.status.in_(_TERMINAL_STATES), PipelineRun.started_at >= _stale_cutoff(db))
        .order_by(PipelineRun.started_at.desc())
        .all()
    )


_IST = timezone(timedelta(hours=5, minutes=30))      # India has no daylight saving: a fixed offset is exact


def _aware(dt: datetime) -> datetime:
    """SQLite (tests) hands back naive datetimes; they are UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _ist_text(dt: datetime) -> str:
    """'10-11-2026, 08:15 PM IST', the same DD-MM-YYYY style as the dashboard."""
    t = _aware(dt).astimezone(_IST)
    return f"{t:%d-%m-%Y}, {t:%I:%M %p} IST"


def _wait_text(seconds: float) -> str:
    minutes = max(1, int(-(-seconds // 60)))
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if h else f"{m} min"


def check_run_limits(db: Session, client_id, now: Optional[datetime] = None) -> Optional[PipelineStartError]:
    """The Run Pipeline limits for a CLIENT user (the caller skips this for a super admin): at most one run per client every
    PIPELINE_COOLDOWN_HOURS hours and PIPELINE_MAX_RUNS_PER_DAY runs in any rolling 24 hours. None if a run may start now, else a 429 that
    names the time of the next allowed run (IST). Counts every run of the client from any user and any status except one that never
    started because the broker was unreachable. Read-only."""
    cooldown_h = float(settings.PIPELINE_COOLDOWN_HOURS or 0)
    per_day = int(settings.PIPELINE_MAX_RUNS_PER_DAY or 0)
    if cooldown_h <= 0 and per_day <= 0:
        return None
    now = _aware(now) if now else datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    since_q = since.replace(tzinfo=None) if db.get_bind().dialect.name == "sqlite" else since
    rows = (
        db.query(PipelineRun.started_at, PipelineRun.error_detail)
        .filter(PipelineRun.client_id == str(client_id), PipelineRun.started_at >= since_q)
        .order_by(PipelineRun.started_at.desc())
        .all()
    )
    starts = [_aware(r.started_at) for r in rows if not (r.error_detail or "").startswith("Failed to dispatch")]
    if not starts:
        return None
    waits, reasons = [], []
    if cooldown_h > 0:
        ready = starts[0] + timedelta(hours=cooldown_h)
        if ready > now:
            waits.append(ready)
            reasons.append(f"one run every {cooldown_h:g} hours")
    if per_day > 0 and len(starts) >= per_day:
        ready = starts[per_day - 1] + timedelta(hours=24)       # the run that has to age out of the 24 hours first
        if ready > now:
            waits.append(ready)
            reasons.append(f"at most {per_day} runs a day")
    if not waits:
        return None
    next_ok = max(waits)
    seconds = (next_ok - now).total_seconds()
    client = db.query(Client).filter(Client.id == client_id).first()
    name = client.name if client else "this company"
    detail = (f"Run limit for {name}: {' and '.join(reasons)}. The last run started {_ist_text(starts[0])}. "
              f"The next run is allowed from {_ist_text(next_ok)} (in {_wait_text(seconds)}). Ask your administrator if you need it sooner.")
    return PipelineStartError(429, detail, retry_after_s=max(1, int(seconds)))


def check_can_start(db: Session, client_id, enforce_limits: bool = False) -> Optional[PipelineStartError]:
    """None if a run for this client may start now, else the refusal. Read-only. enforce_limits=True adds the client-user run limits
    (check_run_limits); the admin CLI and a super admin never pass it."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return PipelineStartError(404, "Client not found")
    runs = active_runs(db)
    mine = next((r for r in runs if str(r.client_id) == str(client_id)), None)
    if mine:
        return PipelineStartError(
            409,
            f"Pipeline already active for this client (run_id={mine.run_id}, stage={mine.stage}, progress={mine.progress_pct}%)",
        )
    if enforce_limits:
        limited = check_run_limits(db, client_id)
        if limited:
            return limited
    if len(runs) >= max(1, int(settings.MAX_CONCURRENT_PIPELINE_RUNS)):
        return PipelineStartError(409, CONCURRENCY_MESSAGE)
    return None


def start_pipeline_run(db: Session, client_id, enforce_limits: bool = False) -> dict:
    """Create the QUEUED run and dispatch it. Raises PipelineStartError (404 / 409 / 429 / 503). enforce_limits=True (the web endpoint,
    for a client user) applies the per-client run limits; the admin CLI and a super admin leave it False."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})   # released at commit/rollback
    refusal = check_can_start(db, client_id, enforce_limits=enforce_limits)
    if refusal:
        db.rollback()
        raise refusal
    client = db.query(Client).filter(Client.id == client_id).first()

    run_id = _uuid.uuid4().hex
    pipeline_run = PipelineRun(
        client_id=str(client_id),
        run_id=run_id,
        status="QUEUED",
        stage="QUEUED",
        progress_pct=0,
        execution_mode="async",
    )
    db.add(pipeline_run)
    db.commit()
    db.refresh(pipeline_run)

    log = logger.bind(run_id=run_id, client_id=str(client_id))
    try:
        # send_task on the configured celery_app (Redis), not a @shared_task binding that may default to AMQP.
        log.debug("celery_broker_url", broker_url=celery_app.conf.broker_url)
        task = celery_app.send_task("app.workers.aggregation_tasks.run_client_pipeline", args=[run_id, str(client_id)])
        log.info("pipeline_queued", celery_task_id=task.id)
    except Exception as exc:
        try:
            pipeline_run.transition("FAILED", f"Failed to dispatch pipeline task: {exc}")
        except ValueError:
            pipeline_run.status = "FAILED"
            pipeline_run.stage = "FAILED"
        pipeline_run.error_detail = f"Failed to dispatch pipeline task: {exc}"
        db.commit()
        log.error("pipeline_dispatch_failed", error=str(exc), exc_info=True)
        raise PipelineStartError(503, "Celery broker unreachable. Pipeline could not be queued.")

    return {
        "run_id": run_id,
        "status": "QUEUED",
        "stage": "QUEUED",
        "progress_pct": 0,
        "client_id": str(client_id),
        "client_name": client.name,
        "message": "Pipeline queued. Poll /pipeline/status for progress.",
    }
