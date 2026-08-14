"""
clients.py — Phase 13 Production Architecture

Pipeline Endpoints
==================

POST /clients/{client_id}/pipeline/run
    - Validates client exists
    - Rejects duplicate active runs (HTTP 409)
    - Creates PipelineRun record (QUEUED)
    - Dispatches run_client_pipeline.delay(run_id, client_id)
    - Returns HTTP 202 with { run_id, status, client_id, client_name }
    - Never blocks. Never inspects Celery internals.

GET /clients/{client_id}/pipeline/status
    - Reads the latest PipelineRun for this client from PostgreSQL
    - Returns: stage, progress_pct, status, started_at, finished_at,
               duration_s, processing_started_at, execution_duration_s,
               current_worker, log_tail, run_id
    - NEVER calls AsyncResult
    - NEVER reads Redis
    - NEVER parses lock metadata

Frontend polling contract:
    POST /run → receive run_id
    Poll GET /status → until status == "SUCCESS" or "FAILED"
    Nothing else.
"""
import uuid as _uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.core.db import get_db
from app.core.celery_app import celery_app
from app.workers.aggregation_tasks import run_client_pipeline
from app.schemas.client import ClientOnboarding, ClientResponse
from app.services.client_service import onboard_client, get_clients, delete_client
from app.models.client import Client
from app.models.pipeline_run import PipelineRun

router = APIRouter()
logger = structlog.get_logger()

# Active pipeline statuses (non-terminal)
_ACTIVE_STATUSES = {
    "QUEUED", "COLLECTING", "PROCESSING", "TREND", "RISK",
    "ALERT", "NARRATIVE", "REPUTATION", "EXECUTIVE", "BENCHMARK", "FINALIZING",
}


# ---------------------------------------------------------------------------
# Standard client endpoints (unchanged)
# ---------------------------------------------------------------------------

@router.post("/onboard", response_model=ClientResponse)
def onboard_new_client(onboarding_data: ClientOnboarding, db: Session = Depends(get_db)):
    """
    Onboard a new client. Automates creation of the client,
    its primary entity, aliases, and generates an initial suite of keywords.
    """
    return onboard_client(db, onboarding_data)


@router.get("/", response_model=List[ClientResponse])
def read_clients(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return get_clients(db, skip, limit, search=search)


@router.delete("/{client_id}")
def delete_client_endpoint(client_id: UUID, db: Session = Depends(get_db)):
    """
    Permanently delete a client and ALL associated intelligence data.
    This operation is irreversible.
    """
    return delete_client(db, client_id)


# ---------------------------------------------------------------------------
# Pipeline endpoints — Phase 13
# ---------------------------------------------------------------------------

@router.post("/{client_id}/pipeline/run", status_code=202)
def trigger_client_pipeline(client_id: UUID, db: Session = Depends(get_db)):
    """
    Queue the intelligence pipeline for a single client.

    Returns HTTP 202 immediately. The pipeline runs asynchronously.
    Poll GET /clients/{client_id}/pipeline/status for progress.

    Errors:
        404  — Client not found
        409  — Pipeline already active for this client
        503  — Celery broker unreachable
    """
    # 1. Validate client
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # 2. Reject duplicate active runs (DB-only check — no Redis needed)
    active_run = db.query(PipelineRun).filter(
        PipelineRun.client_id == str(client_id),
        PipelineRun.status.in_(_ACTIVE_STATUSES),
    ).order_by(PipelineRun.started_at.desc()).first()

    if active_run:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline already active for this client (run_id={active_run.run_id}, stage={active_run.stage}, progress={active_run.progress_pct}%)",
        )

    # 3. Create PipelineRun record — this IS the source of truth from now on
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

    # 4. Dispatch Celery task
    try:
        # Use send_task to explicitly use the configured celery_app (Redis)
        # instead of relying on @shared_task thread-local bindings which may default to AMQP.
        log.debug("celery_broker_url", broker_url=celery_app.conf.broker_url)
        task = celery_app.send_task(
            "app.workers.aggregation_tasks.run_client_pipeline",
            args=[run_id, str(client_id)]
        )
        log.info("pipeline_queued", celery_task_id=task.id)
    except Exception as exc:
        # If dispatch fails, mark the run as failed immediately
        # Use the transition method to ensure finished_at and duration_s are set
        try:
            pipeline_run.transition("FAILED", f"Failed to dispatch pipeline task: {exc}")
        except ValueError:
            pipeline_run.status = "FAILED"
            pipeline_run.stage = "FAILED"

        pipeline_run.error_detail = f"Failed to dispatch pipeline task: {exc}"
        db.commit()
        log.error("pipeline_dispatch_failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Celery broker unreachable. Pipeline could not be queued.",
        )

    # 5. Return 202 immediately — worker executes independently
    return {
        "run_id": run_id,
        "status": "QUEUED",
        "stage": "QUEUED",
        "progress_pct": 0,
        "client_id": str(client_id),
        "client_name": client.name,
        "message": "Pipeline queued. Poll /pipeline/status for progress.",
    }


@router.get("/{client_id}/pipeline/status")
def get_client_pipeline_status(client_id: UUID, db: Session = Depends(get_db)):
    """
    Return current pipeline execution status for a client.

    Reads ONLY from the pipeline_runs table.
    Never calls AsyncResult.
    Never reads Redis.
    Never inspects lock metadata.

    Response shape:
        {
            "run_id": str | null,
            "status": "QUEUED" | "COLLECTING" | ... | "SUCCESS" | "FAILED" | "idle",
            "stage": str,
            "progress_pct": int,
            "started_at": ISO8601 | null,
            "finished_at": ISO8601 | null,
            "duration_s": float | null,  # queue-wait + execution combined
            "processing_started_at": ISO8601 | null,  # when execution actually began
            "execution_duration_s": float | null,  # execution only
            "current_worker": str | null,
            "log_tail": str | null,
            "client_id": str,
        }
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get the most recent run for this client
    latest_run = db.query(PipelineRun).filter(
        PipelineRun.client_id == str(client_id),
    ).order_by(PipelineRun.started_at.desc()).first()

    if not latest_run:
        return {
            "run_id": None,
            "status": "idle",
            "stage": "idle",
            "progress_pct": 0,
            "started_at": None,
            "finished_at": None,
            "duration_s": None,
            "processing_started_at": None,
            "execution_duration_s": None,
            "current_worker": None,
            "log_tail": None,
            "client_id": str(client_id),
        }

    return {
        "run_id": latest_run.run_id,
        "status": latest_run.status,
        "stage": latest_run.stage,
        "progress_pct": latest_run.progress_pct,
        "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
        "finished_at": latest_run.finished_at.isoformat() if latest_run.finished_at else None,
        # Item 18: duration_s is queue-wait + execution combined (measured
        # from row-creation/QUEUED time). execution_duration_s is worker
        # execution only, from when the lock was actually acquired. Both are
        # kept — duration_s is the existing wall-clock contract, unchanged.
        "duration_s": latest_run.duration_s,
        "processing_started_at": latest_run.processing_started_at.isoformat() if latest_run.processing_started_at else None,
        "execution_duration_s": latest_run.execution_duration_s,
        "current_worker": latest_run.current_worker,
        "log_tail": latest_run.log_tail,
        "client_id": str(client_id),
        "error_detail": latest_run.error_detail if latest_run.status == "FAILED" else None,
    }


@router.get("/{client_id}/pipeline/{run_id}")
def get_pipeline_run_by_id(client_id: UUID, run_id: str, db: Session = Depends(get_db)):
    """
    Return a specific pipeline run by run_id.
    Useful when the frontend tracks a specific run_id from the POST /run response.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    run = db.query(PipelineRun).filter(
        PipelineRun.run_id == run_id,
        PipelineRun.client_id == str(client_id),
    ).first()

    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    return {
        "run_id": run.run_id,
        "status": run.status,
        "stage": run.stage,
        "progress_pct": run.progress_pct,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_s": run.duration_s,
        "processing_started_at": run.processing_started_at.isoformat() if run.processing_started_at else None,
        "execution_duration_s": run.execution_duration_s,
        "current_worker": run.current_worker,
        "log_tail": run.log_tail,
        "client_id": str(client_id),
        "error_detail": run.error_detail if run.status == "FAILED" else None,
    }
