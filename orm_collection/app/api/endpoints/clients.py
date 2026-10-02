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
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.core.auth import get_current_user, require_client_access
from app.core.db import get_db
from app.core.rate_limit import limiter, STRICT_RATE_LIMIT
from app.workers.aggregation_tasks import run_client_pipeline
from app.services.pipeline_service import PipelineStartError, start_pipeline_run
from app.schemas.client import ClientOnboarding, ClientResponse
from app.services.client_service import onboard_client, get_clients, delete_client
from app.models.client import Client
from app.models.pipeline_run import PipelineRun
from app.models.user import ROLE_SUPER_ADMIN, User, UserClientAccess

router = APIRouter()
logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Standard client endpoints (unchanged)
# ---------------------------------------------------------------------------

@router.post("/onboard", response_model=ClientResponse)
def onboard_new_client(
    onboarding_data: ClientOnboarding,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Onboard a new client. Automates creation of the client,
    its primary entity, aliases, and generates an initial suite of keywords.

    The onboarding user is automatically granted access to the new client
    (TASK_AUTH.md fix #1/#4) -- otherwise nobody could see a client they just
    created.
    """
    client = onboard_client(db, onboarding_data)
    db.add(UserClientAccess(user_id=current_user.id, client_id=client.id))
    db.commit()
    return client


@router.get("/", response_model=List[ClientResponse])
def read_clients(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # super_admin sees every client (TASK_ROLES.md -- same bypass as
    # require_client_access) -- they hold no user_client_access rows by
    # design, so without this bypass they'd see zero clients everywhere,
    # including their own admin-panel client picker for inviting users.
    if current_user.role == ROLE_SUPER_ADMIN:
        return get_clients(db, skip, limit, search=search)

    # Only clients this user is explicitly granted (TASK_AUTH.md fix #4) --
    # the tenant dropdown must never show a client the caller isn't
    # authorized for, even in a list endpoint with no single client_id param.
    accessible_ids = [
        row.client_id
        for row in db.query(UserClientAccess.client_id).filter(UserClientAccess.user_id == current_user.id).all()
    ]
    if not accessible_ids:
        return []
    return get_clients(db, skip, limit, search=search, client_ids=accessible_ids)


@router.delete("/{client_id}")
def delete_client_endpoint(
    client_id: UUID,
    db: Session = Depends(get_db),
    _access: UUID = Depends(require_client_access),
):
    """
    Permanently delete a client and ALL associated intelligence data.
    This operation is irreversible.
    """
    return delete_client(db, client_id)


# ---------------------------------------------------------------------------
# Pipeline endpoints — Phase 13
# ---------------------------------------------------------------------------

@router.post("/{client_id}/pipeline/run", status_code=202)
@limiter.limit(STRICT_RATE_LIMIT)
def trigger_client_pipeline(
    request: Request,
    response: Response,
    client_id: UUID,
    db: Session = Depends(get_db),
    _access: UUID = Depends(require_client_access),
):
    """
    Queue the intelligence pipeline for a single client.

    Returns HTTP 202 immediately. The pipeline runs asynchronously.
    Poll GET /clients/{client_id}/pipeline/status for progress.

    Errors:
        404  — Client not found
        409  — Pipeline already active for this client, or another client's pipeline is running
        503  — Celery broker unreachable
    """
    # The steps (validate client, reject a duplicate/concurrent run, create the QUEUED PipelineRun, dispatch run_client_pipeline)
    # live in services/pipeline_service.py, shared with scripts/run_pipeline.py.
    try:
        return start_pipeline_run(db, client_id)
    except PipelineStartError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/{client_id}/pipeline/status")
def get_client_pipeline_status(
    client_id: UUID,
    db: Session = Depends(get_db),
    _access: UUID = Depends(require_client_access),
):
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
def get_pipeline_run_by_id(
    client_id: UUID,
    run_id: str,
    db: Session = Depends(get_db),
    _access: UUID = Depends(require_client_access),
):
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
