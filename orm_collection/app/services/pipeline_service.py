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

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


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


def check_can_start(db: Session, client_id) -> Optional[PipelineStartError]:
    """None if a run for this client may start now, else the refusal. Read-only."""
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
    if len(runs) >= max(1, int(settings.MAX_CONCURRENT_PIPELINE_RUNS)):
        return PipelineStartError(409, CONCURRENCY_MESSAGE)
    return None


def start_pipeline_run(db: Session, client_id) -> dict:
    """Create the QUEUED run and dispatch it. Raises PipelineStartError (404 / 409 / 503)."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})   # released at commit/rollback
    refusal = check_can_start(db, client_id)
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
