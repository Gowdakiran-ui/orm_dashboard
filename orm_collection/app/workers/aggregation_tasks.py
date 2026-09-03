"""
aggregation_tasks.py — Phase 13 Production Architecture

Architecture
============
This module contains two categories of tasks:

1. SCHEDULER TASKS (unchanged from previous phases):
   Celery Beat tasks that run on a schedule for all clients.
   These are completely independent of the pipeline orchestrator.
   - calculate_client_trends
   - calculate_client_risks
   - calculate_document_risk
   - evaluate_alerts
   - calculate_narratives
   - calculate_reputation_score
   - calculate_executive_reputation
   - calculate_competitor_benchmarks

2. PIPELINE ORCHESTRATOR (Phase 14 rewrite — stage delegation):
   run_client_pipeline — lightweight Celery task, triggered manually by
   the API, that creates no real work itself. It acquires the per-client
   lock and kicks off a Celery `chain` of per-stage tasks, each routed to
   the queue matching its resource profile (io/nlp/aggregation), then
   returns. This task NEVER calls scheduler tasks and scheduler tasks
   NEVER call this task.

   Phase 13 ran every stage inline inside run_client_pipeline itself, on
   celery-worker-pipeline (--pool=solo --concurrency=1). That meant two
   different clients' manual runs were strictly serialized through one
   process platform-wide, and it duplicated intelligence_tasks.py's
   ~1.6GB transformer model load into the pipeline worker (the exact
   memory-isolation problem celery-worker-nlp was split out to solve —
   see FORENSICS/diagnosis: "Concurrent Pipeline Runs Across Users Don't
   Work"). Phase 14 fixes this by delegating each stage to its own task
   on its own queue, so celery-worker-pipeline goes back to being pure
   orchestration and stages for different clients can run concurrently
   on the shared io/nlp/aggregation worker pools.

Pipeline Execution Model
========================
    API POST /run
        ↓ creates PipelineRun record (QUEUED)
        ↓ dispatches run_client_pipeline.delay(run_id, client_id)
        ↓ returns HTTP 202 immediately

    Worker executes run_client_pipeline (pipeline_queue, orchestration only):
        Acquire Redis lock (NX, 2h TTL)
        ↓ build chain(...) and apply_async(link_error=...)
        ↓ returns immediately — does NOT wait for the chain

    Chain (each link is its own Celery task on its own queue; each link
    performs its own PipelineRun FSM transition/progress update on entry,
    since no single process spans the whole run anymore):
        ↓ COLLECTING   (io_queue)           (5%  → 20%)
        ↓ PROCESSING   (nlp_queue)          (20% → 40%)
        ↓ TREND        (aggregation_queue)  (40% → 50%)
        ↓ RISK         (aggregation_queue)  (50% → 60%)
        ↓ ALERT        (aggregation_queue)  (60% → 70%)
        ↓ NARRATIVE    (aggregation_queue)  (70% → 80%)
        ↓ REPUTATION   (aggregation_queue)  (80% → 85%)
        ↓ EXECUTIVE    (aggregation_queue)  (85% → 90%)
        ↓ BENCHMARK    (aggregation_queue)  (90% → 95%)
        ↓ FINALIZING   (pipeline_queue)     (95% → 100%)
        ↓ SUCCESS, release Redis lock

    On any stage failure (Celery aborts the chain automatically):
        → link_error callback fires (pipeline_queue) → FAILED, persist
          error, release Redis lock, stop. Fires exactly once, since a
          chain runs at most one failing task before aborting.

State is stored in PipelineRun (PostgreSQL).
Status endpoint reads only PipelineRun — never Redis, never AsyncResult.

Locking
=======
    Key:    pipeline:lock:{client_id}
    Value:  JSON { run_id, owner_id, acquired_at }
    TTL:    7200 seconds (2 hours)
    Mode:   SET NX (atomic, race-condition safe)
    Release: GET → verify owner_id → DELETE

    Acquired exactly once, in run_client_pipeline, before the chain is
    dispatched. owner_id is threaded through every stage task's args (not
    stored on PipelineRun — no schema change) so whichever task ends the
    run — pipeline_stage_finalize on success, or
    pipeline_stage_error_handler on failure/dispatch-failure — can
    release it with the same owner_id. Exactly one of those three paths
    runs per pipeline execution, so release happens exactly once.

No heartbeat thread. 2h TTL is sufficient for any realistic pipeline run.
"""
from __future__ import annotations

import json
import math
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

import structlog
from celery import shared_task, chain

from app.core.db import SessionLocal
from app.models.client import Client
from app.models.pipeline_run import PipelineRun
from app.models.trend_state import TrendClientState

logger = structlog.get_logger()


# ===========================================================================
# SECTION 1 — SCHEDULER TASKS (unchanged, completely independent)
# ===========================================================================

# ---------------------------------------------------------------------------
# Supporting helpers for scheduler tasks
# ---------------------------------------------------------------------------

from app.services.intelligence.trend_detector import TrendDetector
from app.services.intelligence.risk_engine import RiskEngine

trend_detector = TrendDetector()
risk_engine = RiskEngine()

TREND_CLIENT_MAX_RETRIES = 3
TREND_CLIENT_BASE_BACKOFF_S = 1.0
TREND_CLIENT_MAX_BACKOFF_S = 10.0

TRANSIENT_ERROR_PATTERNS = (
    "deadlock",
    "timeout",
    "connection",
    "operational",
    "could not obtain lock",
    "serialization failure",
)


def _is_transient_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(pattern in msg for pattern in TRANSIENT_ERROR_PATTERNS)


def _exponential_backoff(attempt: int) -> float:
    backoff = TREND_CLIENT_BASE_BACKOFF_S * math.pow(2, attempt - 1)
    return min(backoff, TREND_CLIENT_MAX_BACKOFF_S)


def _process_single_client_with_retry(client_id, run_id, batch_id, worker_id, log):
    attempt = 0
    last_exc = None
    while attempt <= TREND_CLIENT_MAX_RETRIES:
        if attempt > 0:
            backoff = _exponential_backoff(attempt)
            log.info("trend_client_retrying", client_id=client_id, attempt=attempt, backoff_s=backoff)
            time.sleep(backoff)
            state_db = SessionLocal()
            try:
                state = state_db.query(TrendClientState).filter(
                    TrendClientState.client_id == client_id
                ).first()
                if state:
                    state.processing_status = "TREND_RETRYING"
                    state.retry_count = attempt
                    state.last_retry_at = datetime.now(timezone.utc)
                    state_db.commit()
            except Exception:
                state_db.rollback()
            finally:
                state_db.close()

        client_db = SessionLocal()
        t0 = time.perf_counter()
        try:
            trend_detector.detect_trends(client_db, client_id, run_id=run_id, batch_id=batch_id)
            latency_ms = (time.perf_counter() - t0) * 1000
            return {"client_id": client_id, "status": "success", "retry_count": attempt, "error": None, "latency_ms": round(latency_ms, 2)}
        except Exception as exc:
            client_db.rollback()
            latency_ms = (time.perf_counter() - t0) * 1000
            last_exc = exc
            log.error("trend_client_attempt_failed", client_id=client_id, attempt=attempt, error=str(exc))
            if not _is_transient_error(exc):
                break
            attempt += 1
        finally:
            client_db.close()

    return {"client_id": client_id, "status": "failed", "retry_count": attempt, "error": str(last_exc) if last_exc else "unknown", "latency_ms": None}


@shared_task(bind=True, queue="aggregation_queue")
def calculate_client_trends(self):
    """Trend Detection batch task — runs on schedule for ALL clients."""
    run_id = uuid.uuid4().hex
    batch_id = uuid.uuid4().hex[:12]
    worker_id = os.getpid()
    log = logger.bind(run_id=run_id, batch_id=batch_id, worker_id=worker_id, task="calculate_client_trends")
    log.info("trend_batch_started")
    t_batch_start = time.perf_counter()

    try:
        list_db = SessionLocal()
        try:
            clients = list_db.query(Client).all()
            client_ids = [str(c.id) for c in clients]
        finally:
            list_db.close()
    except Exception as exc:
        log.error("trend_batch_client_list_failed", error=str(exc), exc_info=True)
        raise self.retry(exc=exc, countdown=300)

    if not client_ids:
        log.info("trend_batch_no_clients")
        return

    results = []
    for client_id in client_ids:
        result = _process_single_client_with_retry(client_id, run_id, batch_id, worker_id, log.bind(client_id=client_id))
        results.append(result)

    failed = [r for r in results if r["status"] == "failed"]
    log.info("trend_batch_complete",
             total=len(client_ids),
             success=len(results) - len(failed),
             failed=len(failed),
             latency_ms=round((time.perf_counter() - t_batch_start) * 1000, 2))


# ---------------------------------------------------------------------------
# Risk Engine scheduler task
# ---------------------------------------------------------------------------

def _process_single_client_risk_with_retry(client_id, run_id, batch_id, worker_id, log):
    attempt = 1
    last_exc = None
    max_retries = 3
    while attempt <= max_retries + 1:
        if attempt > 1:
            backoff = min(1.0 * math.pow(2, attempt - 2), 10.0)
            log.info("risk_client_retrying", client_id=client_id, attempt=attempt - 1, backoff_s=backoff)
            time.sleep(backoff)
            state_db = SessionLocal()
            try:
                state = risk_engine._get_or_create_state(state_db, client_id)
                risk_engine._transition_state(state_db, state, "RISK_RETRYING", run_id=run_id, batch_id=batch_id, error=str(last_exc), log=log)
                state.retry_count = attempt - 1
                state.last_retry_at = datetime.now(timezone.utc)
                state_db.commit()
            except Exception as se:
                state_db.rollback()
                log.error("risk_state_retry_update_failed", error=str(se))
            finally:
                state_db.close()

        client_db = SessionLocal()
        t0 = time.perf_counter()
        try:
            risk_engine.process_client(client_db, client_id, run_id=run_id, batch_id=batch_id, attempt=attempt)
            latency_ms = (time.perf_counter() - t0) * 1000
            return {"client_id": client_id, "status": "success", "retry_count": attempt - 1, "error": None, "latency_ms": round(latency_ms, 2)}
        except Exception as exc:
            client_db.rollback()
            last_exc = exc
            log.error("risk_client_attempt_failed", client_id=client_id, attempt=attempt, error=str(exc))
            if not _is_transient_error(exc):
                break
            attempt += 1
        finally:
            client_db.close()

    state_db = SessionLocal()
    try:
        state = risk_engine._get_or_create_state(state_db, client_id)
        risk_engine._transition_state(state_db, state, "RISK_FAILED", run_id=run_id, batch_id=batch_id, error=str(last_exc), log=log)
        state_db.commit()
    except Exception:
        state_db.rollback()
    finally:
        state_db.close()
    return {"client_id": client_id, "status": "failed", "retry_count": attempt - 1, "error": str(last_exc) if last_exc else "unknown", "latency_ms": None}


@shared_task(bind=True, queue="aggregation_queue")
def calculate_client_risks(self):
    """Risk Engine batch task — runs on schedule for ALL clients."""
    run_id = uuid.uuid4().hex
    batch_id = uuid.uuid4().hex[:12]
    worker_id = str(os.getpid())
    log = logger.bind(run_id=run_id, batch_id=batch_id, worker_id=worker_id, task="calculate_client_risks")
    log.info("risk_batch_started")
    t_batch_start = time.perf_counter()

    try:
        list_db = SessionLocal()
        try:
            clients = list_db.query(Client).all()
            client_ids = [str(c.id) for c in clients]
        finally:
            list_db.close()
    except Exception as exc:
        log.error("risk_batch_client_list_failed", error=str(exc), exc_info=True)
        raise self.retry(exc=exc, countdown=300)

    if not client_ids:
        return

    results = [_process_single_client_risk_with_retry(cid, run_id, batch_id, worker_id, log.bind(client_id=cid)) for cid in client_ids]
    failed = [r for r in results if r["status"] == "failed"]
    log.info("risk_batch_complete", total=len(client_ids), success=len(results) - len(failed), failed=len(failed),
             latency_ms=round((time.perf_counter() - t_batch_start) * 1000, 2))


@shared_task(bind=True, queue="aggregation_queue")
def calculate_document_risk(self, document_id: str):
    db = SessionLocal()
    try:
        risk_engine.calculate_document_risk(db, document_id)
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=300)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Alert Engine scheduler task
# ---------------------------------------------------------------------------

from app.services.intelligence.alert_engine import AlertEngine
alert_engine = AlertEngine()


@shared_task(bind=True, max_retries=3)
def evaluate_alerts(self):
    """
    Alert Engine batch task — runs on schedule for ALL clients.

    Retry/backoff pattern 4 of 4 in this codebase (FINDINGS.md #18): the only
    task that inspects *why* a client failed (_is_transient_error below)
    before deciding to retry at all, using its own exponential formula
    (30 * 2**retries), distinct from every other task's unconditional retry.
    The other 3 patterns: Celery exponential backoff (document_processor.py,
    collection_tasks.py, search_tasks.py), Celery flat countdown (this file's
    other tasks, intelligence_tasks.py), and in-process retry classes
    (RetryConfig/SentimentRetryConfig/TopicRetryConfig). Intentional
    per-task variance, not drift -- not consolidated this phase.
    """
    from celery.exceptions import Retry
    run_id = uuid.uuid4().hex
    batch_id = uuid.uuid4().hex[:12]
    attempt = self.request.retries + 1

    try:
        list_db = SessionLocal()
        try:
            clients = list_db.query(Client).all()
            client_ids = [str(c.id) for c in clients]
        finally:
            list_db.close()
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)

    failed_clients = []
    for cid in client_ids:
        client_db = SessionLocal()
        try:
            alert_engine.process_client(client_db, cid, run_id=run_id, batch_id=batch_id, attempt=attempt)
            client_db.commit()
        except Exception as exc:
            client_db.rollback()
            failed_clients.append(exc)
        finally:
            client_db.close()

    try:
        if failed_clients:
            from app.services.intelligence.alert_engine import _is_transient_error as _alert_transient
            has_transient = any(_alert_transient(exc) for exc in failed_clients)
            if has_transient and self.request.retries < 3:
                countdown = 30 * (2 ** self.request.retries)
                raise self.retry(exc=failed_clients[0], countdown=countdown)
            else:
                raise failed_clients[0]
    except Retry:
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


# ---------------------------------------------------------------------------
# Narrative Engine scheduler task
# ---------------------------------------------------------------------------

from app.services.intelligence.narrative_engine import NarrativeEngine, NarrativeStateMachine
narrative_engine = NarrativeEngine()


def _process_single_client_narrative_with_retry(client_id, run_id, batch_id, worker_id, log):
    attempt = 1
    last_exc = None
    max_retries = 3
    while attempt <= max_retries + 1:
        if attempt > 1:
            backoff = min(1.0 * math.pow(2, attempt - 2), 10.0)
            time.sleep(backoff)
            state_db = SessionLocal()
            try:
                client = state_db.query(Client).filter(Client.id == client_id).first()
                if client:
                    NarrativeStateMachine.transition(state_db, client, NarrativeStateMachine.RETRYING, run_id=run_id, batch_id=batch_id, failure_reason=str(last_exc), retry_count=attempt - 1)
                    state_db.commit()
            except Exception:
                state_db.rollback()
            finally:
                state_db.close()

        client_db = SessionLocal()
        t0 = time.perf_counter()
        try:
            client = client_db.query(Client).filter(Client.id == client_id).with_for_update().first()
            if client:
                NarrativeStateMachine.transition(client_db, client, NarrativeStateMachine.PROCESSING, run_id=run_id, batch_id=batch_id, retry_count=attempt - 1)
                client_db.commit()
            narrative_engine.process_client(client_db, client_id, run_id=run_id, batch_id=batch_id, worker_id=worker_id, attempt=attempt - 1)
            client = client_db.query(Client).filter(Client.id == client_id).first()
            if client:
                latency_ms = (time.perf_counter() - t0) * 1000
                NarrativeStateMachine.transition(client_db, client, NarrativeStateMachine.COMPLETE, run_id=run_id, batch_id=batch_id, latency_ms=latency_ms)
                client_db.commit()
            return {"client_id": client_id, "status": "success", "retry_count": attempt - 1, "error": None, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
        except Exception as exc:
            client_db.rollback()
            last_exc = exc
            if not _is_transient_error(exc):
                break
            attempt += 1
        finally:
            client_db.close()

    state_db = SessionLocal()
    try:
        client = state_db.query(Client).filter(Client.id == client_id).first()
        if client:
            NarrativeStateMachine.transition(state_db, client, NarrativeStateMachine.FAILED, run_id=run_id, batch_id=batch_id, failure_reason=str(last_exc), retry_count=attempt - 1)
            state_db.commit()
    except Exception:
        state_db.rollback()
    finally:
        state_db.close()
    return {"client_id": client_id, "status": "failed", "retry_count": attempt - 1, "error": str(last_exc) if last_exc else "unknown", "latency_ms": None}


@shared_task(bind=True, queue="aggregation_queue")
def calculate_narratives(self):
    """Narrative Engine batch task — runs on schedule for ALL clients."""
    run_id = uuid.uuid4().hex
    batch_id = uuid.uuid4().hex[:12]
    worker_id = str(os.getpid())
    log = logger.bind(run_id=run_id, batch_id=batch_id, worker_id=worker_id, task="calculate_narratives")
    log.info("narrative_batch_started")
    t_batch_start = time.perf_counter()

    try:
        list_db = SessionLocal()
        try:
            clients = list_db.query(Client).all()
            client_ids = [str(c.id) for c in clients]
        finally:
            list_db.close()
    except Exception as exc:
        log.error("narrative_batch_client_list_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)

    if not client_ids:
        return

    results = [_process_single_client_narrative_with_retry(cid, run_id, batch_id, worker_id, log.bind(client_id=cid)) for cid in client_ids]
    failed = [r for r in results if r["status"] == "failed"]
    log.info("narrative_batch_complete", total=len(client_ids), success=len(results) - len(failed), failed=len(failed),
             latency_ms=round((time.perf_counter() - t_batch_start) * 1000, 2))


# ---------------------------------------------------------------------------
# Reputation Engine scheduler task
# ---------------------------------------------------------------------------

from app.services.intelligence.reputation_engine import ReputationEngine, ReputationStateMachine
reputation_engine = ReputationEngine()


def _process_single_client_reputation_with_retry(client_id, run_id, batch_id, worker_id, log):
    attempt = 1
    last_exc = None
    max_retries = 3
    while attempt <= max_retries + 1:
        if attempt > 1:
            backoff = min(1.0 * math.pow(2, attempt - 2), 10.0)
            time.sleep(backoff)
            state_db = SessionLocal()
            try:
                client = state_db.query(Client).filter(Client.id == client_id).first()
                if client:
                    ReputationStateMachine.transition(state_db, client, ReputationStateMachine.RETRYING, run_id=run_id, batch_id=batch_id, failure_reason=str(last_exc), retry_count=attempt - 1)
                    state_db.commit()
            except Exception:
                state_db.rollback()
            finally:
                state_db.close()

        client_db = SessionLocal()
        t0 = time.perf_counter()
        try:
            client = client_db.query(Client).filter(Client.id == client_id).with_for_update().first()
            if client:
                ReputationStateMachine.transition(client_db, client, ReputationStateMachine.PROCESSING, run_id=run_id, batch_id=batch_id, retry_count=attempt - 1)
                client_db.commit()
            reputation_engine.process_client(client_db, client_id, run_id=run_id, batch_id=batch_id, worker_id=worker_id, attempt=attempt - 1)
            client = client_db.query(Client).filter(Client.id == client_id).first()
            if client:
                latency_ms = (time.perf_counter() - t0) * 1000
                ReputationStateMachine.transition(client_db, client, ReputationStateMachine.COMPLETE, run_id=run_id, batch_id=batch_id, latency_ms=latency_ms)
                client_db.commit()
            return {"client_id": client_id, "status": "success", "retry_count": attempt - 1, "error": None, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
        except Exception as exc:
            client_db.rollback()
            last_exc = exc
            if not _is_transient_error(exc):
                break
            attempt += 1
        finally:
            client_db.close()

    state_db = SessionLocal()
    try:
        client = state_db.query(Client).filter(Client.id == client_id).first()
        if client:
            ReputationStateMachine.transition(state_db, client, ReputationStateMachine.FAILED, run_id=run_id, batch_id=batch_id, failure_reason=str(last_exc), retry_count=attempt - 1)
            state_db.commit()
    except Exception:
        state_db.rollback()
    finally:
        state_db.close()
    return {"client_id": client_id, "status": "failed", "retry_count": attempt - 1, "error": str(last_exc) if last_exc else "unknown", "latency_ms": None}


@shared_task(bind=True, queue="aggregation_queue")
def calculate_reputation_score(self):
    """Reputation Engine batch task — runs on schedule for ALL clients."""
    run_id = uuid.uuid4().hex
    batch_id = uuid.uuid4().hex[:12]
    worker_id = str(os.getpid())
    log = logger.bind(run_id=run_id, batch_id=batch_id, worker_id=worker_id, task="calculate_reputation_score")
    log.info("reputation_batch_started")
    t_batch_start = time.perf_counter()

    try:
        list_db = SessionLocal()
        try:
            clients = list_db.query(Client).all()
            client_ids = [str(c.id) for c in clients]
        finally:
            list_db.close()
    except Exception as exc:
        log.error("reputation_batch_client_list_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)

    if not client_ids:
        return

    results = [_process_single_client_reputation_with_retry(cid, run_id, batch_id, worker_id, log.bind(client_id=cid)) for cid in client_ids]
    failed = [r for r in results if r["status"] == "failed"]
    log.info("reputation_batch_complete", total=len(client_ids), success=len(results) - len(failed), failed=len(failed),
             latency_ms=round((time.perf_counter() - t_batch_start) * 1000, 2))


# ---------------------------------------------------------------------------
# Executive Reputation Engine scheduler task
# ---------------------------------------------------------------------------

from app.services.intelligence.executive_reputation_engine import ExecutiveReputationEngine, ExecutiveReputationStateMachine
exec_reputation_engine = ExecutiveReputationEngine()


def _process_single_client_exec_reputation_with_retry(client_id, run_id, batch_id, worker_id, log):
    attempt = 1
    last_exc = None
    max_retries = 3
    while attempt <= max_retries + 1:
        if attempt > 1:
            backoff = min(1.0 * math.pow(2, attempt - 2), 10.0)
            time.sleep(backoff)
            state_db = SessionLocal()
            try:
                client = state_db.query(Client).filter(Client.id == client_id).first()
                if client:
                    ExecutiveReputationStateMachine.transition(state_db, client, ExecutiveReputationStateMachine.RETRYING, run_id=run_id, batch_id=batch_id, failure_reason=str(last_exc), retry_count=attempt - 1)
                    state_db.commit()
            except Exception:
                state_db.rollback()
            finally:
                state_db.close()

        client_db = SessionLocal()
        t0 = time.perf_counter()
        try:
            client = client_db.query(Client).filter(Client.id == client_id).with_for_update().first()
            if client:
                ExecutiveReputationStateMachine.transition(client_db, client, ExecutiveReputationStateMachine.PROCESSING, run_id=run_id, batch_id=batch_id, retry_count=attempt - 1)
                client_db.commit()
            exec_reputation_engine.process_client(client_db, client_id, run_id=run_id, batch_id=batch_id, worker_id=worker_id, attempt=attempt - 1)
            client = client_db.query(Client).filter(Client.id == client_id).first()
            if client and client.exec_reputation_processing_status != ExecutiveReputationStateMachine.SKIPPED:
                latency_ms = (time.perf_counter() - t0) * 1000
                ExecutiveReputationStateMachine.transition(client_db, client, ExecutiveReputationStateMachine.COMPLETE, run_id=run_id, batch_id=batch_id, latency_ms=latency_ms)
                client_db.commit()
            return {"client_id": client_id, "status": "success", "retry_count": attempt - 1, "error": None, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
        except Exception as exc:
            client_db.rollback()
            last_exc = exc
            if not _is_transient_error(exc):
                break
            attempt += 1
        finally:
            client_db.close()

    state_db = SessionLocal()
    try:
        client = state_db.query(Client).filter(Client.id == client_id).first()
        if client:
            ExecutiveReputationStateMachine.transition(state_db, client, ExecutiveReputationStateMachine.FAILED, run_id=run_id, batch_id=batch_id, failure_reason=str(last_exc), retry_count=attempt - 1)
            state_db.commit()
    except Exception:
        state_db.rollback()
    finally:
        state_db.close()
    return {"client_id": client_id, "status": "failed", "retry_count": attempt - 1, "error": str(last_exc) if last_exc else "unknown", "latency_ms": None}


@shared_task(bind=True, queue="aggregation_queue")
def calculate_executive_reputation(self):
    """Executive Reputation batch task — runs on schedule for ALL clients."""
    run_id = uuid.uuid4().hex
    batch_id = uuid.uuid4().hex[:12]
    worker_id = str(os.getpid())
    log = logger.bind(run_id=run_id, batch_id=batch_id, worker_id=worker_id, task="calculate_executive_reputation")
    log.info("exec_reputation_batch_started")
    t_batch_start = time.perf_counter()

    try:
        list_db = SessionLocal()
        try:
            clients = list_db.query(Client).all()
            client_ids = [str(c.id) for c in clients]
        finally:
            list_db.close()
    except Exception as exc:
        log.error("exec_reputation_batch_client_list_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)

    if not client_ids:
        return

    results = [_process_single_client_exec_reputation_with_retry(cid, run_id, batch_id, worker_id, log.bind(client_id=cid)) for cid in client_ids]
    failed = [r for r in results if r["status"] == "failed"]
    log.info("exec_reputation_batch_complete", total=len(client_ids), success=len(results) - len(failed), failed=len(failed),
             latency_ms=round((time.perf_counter() - t_batch_start) * 1000, 2))


# ---------------------------------------------------------------------------
# Benchmark Engine scheduler task
# ---------------------------------------------------------------------------

from app.services.intelligence.benchmark_engine import BenchmarkEngine, BenchmarkStateMachine
benchmark_engine = BenchmarkEngine()


def _process_single_client_benchmark_with_retry(client_id, run_id, batch_id, worker_id, log):
    attempt = 1
    last_exc = None
    max_retries = 3
    while attempt <= max_retries + 1:
        if attempt > 1:
            backoff = min(1.0 * math.pow(2, attempt - 2), 10.0)
            time.sleep(backoff)
            state_db = SessionLocal()
            try:
                client = state_db.query(Client).filter(Client.id == client_id).first()
                if client:
                    BenchmarkStateMachine.transition(state_db, client, BenchmarkStateMachine.RETRYING, run_id=run_id, batch_id=batch_id, failure_reason=str(last_exc), retry_count=attempt - 1)
                    state_db.commit()
            except Exception:
                state_db.rollback()
            finally:
                state_db.close()

        client_db = SessionLocal()
        t0 = time.perf_counter()
        try:
            client = client_db.query(Client).filter(Client.id == client_id).with_for_update().first()
            if client:
                BenchmarkStateMachine.transition(client_db, client, BenchmarkStateMachine.PROCESSING, run_id=run_id, batch_id=batch_id, retry_count=attempt - 1)
                client_db.commit()
            benchmark_engine.process_client(client_db, client_id, run_id=run_id, batch_id=batch_id, worker_id=worker_id, attempt=attempt - 1)
            client = client_db.query(Client).filter(Client.id == client_id).first()
            if client and client.benchmark_processing_status != BenchmarkStateMachine.SKIPPED:
                latency_ms = (time.perf_counter() - t0) * 1000
                BenchmarkStateMachine.transition(client_db, client, BenchmarkStateMachine.COMPLETE, run_id=run_id, batch_id=batch_id, latency_ms=latency_ms)
                client_db.commit()
            return {"client_id": client_id, "status": "success", "retry_count": attempt - 1, "error": None, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
        except Exception as exc:
            client_db.rollback()
            last_exc = exc
            if not _is_transient_error(exc):
                break
            attempt += 1
        finally:
            client_db.close()

    state_db = SessionLocal()
    try:
        client = state_db.query(Client).filter(Client.id == client_id).first()
        if client:
            BenchmarkStateMachine.transition(state_db, client, BenchmarkStateMachine.FAILED, run_id=run_id, batch_id=batch_id, failure_reason=str(last_exc), retry_count=attempt - 1)
            state_db.commit()
    except Exception:
        state_db.rollback()
    finally:
        state_db.close()
    return {"client_id": client_id, "status": "failed", "retry_count": attempt - 1, "error": str(last_exc) if last_exc else "unknown", "latency_ms": None}


@shared_task(bind=True, queue="aggregation_queue")
def calculate_competitor_benchmarks(self):
    """Benchmark Engine batch task — runs on schedule for ALL clients."""
    run_id = uuid.uuid4().hex
    batch_id = uuid.uuid4().hex[:12]
    worker_id = str(os.getpid())
    log = logger.bind(run_id=run_id, batch_id=batch_id, worker_id=worker_id, task="calculate_competitor_benchmarks")
    log.info("benchmark_batch_started")
    t_batch_start = time.perf_counter()

    try:
        list_db = SessionLocal()
        try:
            clients = list_db.query(Client).all()
            client_ids = [str(c.id) for c in clients]
        finally:
            list_db.close()
    except Exception as exc:
        log.error("benchmark_batch_client_list_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)

    if not client_ids:
        return

    results = [_process_single_client_benchmark_with_retry(cid, run_id, batch_id, worker_id, log.bind(client_id=cid)) for cid in client_ids]
    failed = [r for r in results if r["status"] == "failed"]
    log.info("benchmark_batch_complete", total=len(client_ids), success=len(results) - len(failed), failed=len(failed),
             latency_ms=round((time.perf_counter() - t_batch_start) * 1000, 2))


# ===========================================================================
# SECTION 2 — PIPELINE ORCHESTRATOR (Phase 13)
# ===========================================================================

@dataclass(frozen=True)
class PipelineContext:
    """
    Immutable context passed to every pipeline stage.
    Created once in run_client_pipeline and never reconstructed.
    """
    pipeline_run_id: str       # UUID of the PipelineRun row
    client_id: str             # Client being processed
    run_id: str                # Correlation ID (same as PipelineRun.run_id)
    started_at: datetime
    worker_id: str             # PID-based identifier
    execution_mode: str        # Always "async"
    correlation_id: str        # For log tracing (same as run_id)


# ---------------------------------------------------------------------------
# Lock helpers
# ---------------------------------------------------------------------------

_LOCK_TTL_SECONDS = 7200  # 2 hours — no heartbeat needed


def _acquire_lock(redis_client, client_id: str, run_id: str, owner_id: str) -> bool:
    """
    Atomic SET NX lock.
    Returns True if acquired, False if another run is active.
    """
    lock_key = f"pipeline:lock:{client_id}"
    lock_value = json.dumps({
        "run_id": run_id,
        "owner_id": owner_id,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    })
    result = redis_client.set(lock_key, lock_value, nx=True, ex=_LOCK_TTL_SECONDS)
    return bool(result)


def _release_lock(redis_client, client_id: str, owner_id: str, log) -> None:
    """
    Compare-and-delete: only release if we own the lock.
    Never raises — failure is logged and swallowed.
    """
    lock_key = f"pipeline:lock:{client_id}"
    try:
        raw = redis_client.get(lock_key)
        if not raw:
            return
        raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        data = json.loads(raw_str)
        if data.get("owner_id") == owner_id:
            redis_client.delete(lock_key)
            log.info("pipeline_lock_released", client_id=client_id)
        else:
            log.warning("pipeline_lock_owner_mismatch_on_release",
                        expected=owner_id, actual=data.get("owner_id"))
    except Exception as exc:
        log.error("pipeline_lock_release_error", error=str(exc))


# ---------------------------------------------------------------------------
# PipelineRun state helpers
# ---------------------------------------------------------------------------

def _update_run(db, pipeline_run_id: str, new_stage: str, log_line: str = "") -> bool:
    """
    Advance FSM state in the DB. Uses a fresh session to avoid holding
    a long-lived transaction across slow engine calls.

    Returns True if the run's FSM actually advanced, False if this call was
    ignored as a stale/duplicate no-op (including "no such run"). Callers
    MUST check this and skip their real stage work when it's False -- the
    real chain already did (or is doing) that work under its own task, so
    running it again would silently double-write that stage's results
    (duplicate trend/risk/alert/narrative rows etc.), not just risk a crash.

    Real-run verification of the timeout fix (see _PIPELINE_RUN_TIMEOUT_MINUTES
    above) hit this live: nlp_queue's --pool=solo worker freezes the whole
    process for a long PROCESSING stage's entire duration (no other thread
    can service the Redis connection); a ~2min host network interruption
    during that window caused the connection to drop, and Celery redelivered
    the same already-completed task once it reconnected. The redelivered
    task called _update_run(..., "PROCESSING", ...) a second time while the
    run was already sitting in "PROCESSING" from the first (genuine, already
    succeeded) delivery -- an illegal X->X self-transition that used to crash
    the redelivered task, which then marked an otherwise fully-successful
    89-document run FAILED via the link_error handler, and cascaded into
    every legitimate downstream stage task also failing against the
    now-terminal row.

    2026-09-02 stress test reproduced the predicted gap directly: a
    redelivered app.workers.aggregation_tasks.pipeline_stage_process
    (same Celery task ID, executed twice, confirmed via duplicate
    "succeeded" log lines with different durations) each triggered their
    own downstream chain link. The first copy's chain legitimately advanced
    TREND -> RISK; the second copy's TREND task then hit the exact "landed
    after the real chain moved past this stage" case this docstring already
    called out, and crashed a run that had actually completed its real work.
    transition() itself now treats "target stage is at or behind the run's
    current position, including past a terminal state" as a no-op instead of
    raising, so this helper's own same-stage check is now redundant with
    that (kept as a fast path / explicit log event) -- see PipelineRun.transition().
    """
    run = db.query(PipelineRun).filter(PipelineRun.run_id == pipeline_run_id).with_for_update().first()
    if not run:
        return False
    if run.status == new_stage:
        logger.warning("pipeline_duplicate_stage_transition_ignored",
                        run_id=pipeline_run_id, stage=new_stage)
        return False
    return run.transition(new_stage, log_line)
    db.commit()


def _fail_run(db, pipeline_run_id: str, error_detail: str, log) -> None:
    """Mark the run as FAILED with full error detail."""
    try:
        run = db.query(PipelineRun).filter(PipelineRun.run_id == pipeline_run_id).with_for_update().first()
        if run and not run.is_terminal:
            run.status = "FAILED"
            run.stage = "FAILED"
            run.error_detail = error_detail[:10000]
            run.log_tail = error_detail[:2000]
            now = datetime.now(timezone.utc)
            run.finished_at = now
            if run.started_at:
                run.duration_s = (now - run.started_at).total_seconds()
            if run.processing_started_at:
                run.execution_duration_s = (now - run.processing_started_at).total_seconds()
            db.commit()
    except Exception as exc:
        db.rollback()
        log.error("pipeline_fail_run_update_error", error=str(exc))


def _update_progress(db, pipeline_run_id: str, progress_pct: int, log_line: str) -> None:
    """
    Item 17: update progress_pct/log_tail *within* a stage, without an FSM
    stage transition. transition() rejects a same-stage "transition" (e.g.
    PROCESSING -> PROCESSING isn't in _ALLOWED_TRANSITIONS), so incremental
    progress needs the same direct-field-set escape hatch _fail_run already
    uses for a different reason. Swallows its own errors so a progress
    update glitch can never abort the actual pipeline stage calling it.
    """
    try:
        run = db.query(PipelineRun).filter(PipelineRun.run_id == pipeline_run_id).with_for_update().first()
        if run and not run.is_terminal:
            run.progress_pct = progress_pct
            if log_line:
                run.log_tail = log_line[:2000]
            db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# PipelineRun watchdog
# ---------------------------------------------------------------------------

_PIPELINE_RUN_TERMINAL = {"SUCCESS", "FAILED"}
# Readiness-report incident: a real 89-document onboarding batch took ~70min
# on nlp_queue's single-concurrency (--pool=solo) worker and got marked
# FAILED at the old 60min threshold despite completing normally -- the old
# comment's "~7-10 min observed" / "591s wall for an 88-doc run" figure was
# from a much lighter/cached test run, not representative of real NLP
# throughput under solo concurrency. Do not raise celery-worker-nlp's
# concurrency to fix this: task-level time_limit is a documented no-op
# under --pool=solo (BasePool.on_soft_timeout/on_hard_timeout are
# unimplemented `pass`), so this watchdog's periodic sweep is the *only*
# real enforcement mechanism for a hung run -- widening it, not narrowing
# it, is the safe direction.
#
# Recalculated from the real measurement, not the stale one:
#   throughput  = 70 min / 89 docs = ~0.79 min/doc
#   design load = 3x today's batch = ~267 docs (a meaningfully larger first
#                 onboarding, not just today's exact size)
#   projected   = 267 * 0.79 ≈ 210 min of real NLP processing time
#   margin      = 1.4x on top of the linear projection, for retry backoff,
#                 DB/Redis latency variance, and the non-NLP stages
#                 (COLLECTING/TREND/RISK/.../FINALIZING) riding on the same
#                 clock ≈ 294 min
#   -> rounded up to 300 min (5h)
#
# This is a fixed constant, not a per-run-document-count formula: PipelineRun
# has no document-count column today (see app/models/pipeline_run.py), and
# adding one is a schema.sql change -- a high-risk-zone edit this close to
# deploy that needs its own fresh-Postgres verification pass. A raised,
# real-margin constant closes the actual incident without that risk; revisit
# true per-document scaling as separate follow-up work, not part of this fix.
_PIPELINE_RUN_TIMEOUT_MINUTES = 300


@shared_task
def pipeline_run_watchdog():
    """
    Watchdog for PipelineRun (Phase 13), mirroring collection_watchdog's
    staleness-sweep pattern in collection_tasks.py. Runs every 15 minutes.

    This is the actual enforcement mechanism for a hung/crashed pipeline run.
    A Celery soft_time_limit/time_limit was considered instead, but
    run_client_pipeline runs under --pool=solo, where time-limit enforcement
    is a no-op: BasePool.on_soft_timeout/on_hard_timeout are unimplemented
    (`pass`) and only the prefork pool overrides them to kill the child
    process. Solo has no child process to kill, so a decorator-level time
    limit would silently do nothing while looking like a real ceiling.
    A Beat-scheduled sweep works regardless of pool type since it acts from
    outside the stuck task.

    Threshold: 300 minutes (5h), recalculated after a real 89-document
    onboarding batch took ~70min and was wrongly marked FAILED at the old
    60min threshold. See _PIPELINE_RUN_TIMEOUT_MINUTES above for the full
    math (throughput -> 3x-batch projection -> margin).
    """
    from datetime import datetime, timezone, timedelta
    import structlog
    from app.utils.redis_client import redis_client

    log = structlog.get_logger().bind(task="pipeline_run_watchdog")
    db = SessionLocal()
    try:
        timeout_limit = datetime.now(timezone.utc) - timedelta(minutes=_PIPELINE_RUN_TIMEOUT_MINUTES)

        stuck_runs = db.query(PipelineRun).filter(
            ~PipelineRun.status.in_(_PIPELINE_RUN_TERMINAL),
            PipelineRun.started_at < timeout_limit,
        ).all()

        if not stuck_runs:
            log.info("watchdog_no_stuck_runs")
            return

        log.warning("watchdog_found_stuck_runs", total_stuck=len(stuck_runs))

        for run in stuck_runs:
            run_id_str = run.run_id
            client_id_str = run.client_id
            log.warning("watchdog_recovering_run", run_id=run_id_str, client_id=client_id_str,
                       status=run.status, stage=run.stage, started_at=str(run.started_at))

            reason = (f"reconciled by pipeline_run_watchdog: stuck in status={run.status} "
                     f"stage={run.stage} past {_PIPELINE_RUN_TIMEOUT_MINUTES}-minute timeout")
            run.status = "FAILED"
            run.stage = "FAILED"
            run.error_detail = reason
            run.log_tail = reason
            now = datetime.now(timezone.utc)
            run.finished_at = now
            if run.started_at:
                run.duration_s = (now - run.started_at).total_seconds()
            if run.processing_started_at:
                run.execution_duration_s = (now - run.processing_started_at).total_seconds()
            db.commit()

            # Release the Phase 13 lock (pipeline:lock:{client_id}) — but only
            # if it still belongs to *this* run_id, so a lock legitimately
            # re-acquired by a newer run in the meantime is never touched.
            lock_key = f"pipeline:lock:{client_id_str}"
            try:
                raw = redis_client.get(lock_key)
                if raw:
                    raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    data = json.loads(raw_str)
                    if data.get("run_id") == run_id_str:
                        redis_client.delete(lock_key)
                        log.warning("watchdog_released_pipeline_lock",
                                   client_id=client_id_str, run_id=run_id_str)
            except Exception as exc:
                log.error("watchdog_lock_release_error", error=str(exc))

    except Exception as exc:
        db.rollback()
        log.error("watchdog_failed", error=str(exc))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Stage functions — each receives PipelineContext, returns stage output
# ---------------------------------------------------------------------------

def _stage_collect(ctx: PipelineContext, db) -> List[str]:
    """
    COLLECTING stage: fetch RSS feeds for this client, deduplicate,
    persist new documents. Returns list of new document IDs.
    """
    from app.models.rss_feed import RSSFeed
    from app.models.source import Source
    from app.models.document import Document
    from app.adapters.rss import RSSAdapter
    from app.adapters.registry import ADAPTER_REGISTRY
    from app.services.document_service import process_and_save_document
    from app.schemas.document import NormalizedDocument
    from app.workers.collection_tasks import _get_or_create_source
    from app.utils.text_processing import canonicalize_url

    log = logger.bind(stage="COLLECTING", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started")

    client = db.query(Client).filter(Client.id == ctx.client_id).first()
    if not client:
        raise ValueError(f"Client {ctx.client_id} not found")

    client_feeds = db.query(RSSFeed).filter(
        RSSFeed.is_active == True,
        RSSFeed.client_id == ctx.client_id
    ).all()

    new_doc_ids: List[str] = []

    for feed in client_feeds:
        source = _get_or_create_source(db, feed)

        adapter_cls = ADAPTER_REGISTRY.get(feed.source_format, RSSAdapter)
        adapter = adapter_cls()

        try:
            entries = adapter.fetch(feed.feed_url)
            for entry in entries:
                norm = adapter.normalize(entry, str(source.id))
                norm_doc = NormalizedDocument(**norm)
                is_saved, _, _ = process_and_save_document(db, norm_doc)
                if is_saved:
                    # Item 20: process_and_save_document() inserts
                    # Document.url as canonicalize_url(doc_data.url), not the
                    # raw URL (document_service.py:24,40) -- looking it back
                    # up by the raw URL silently missed every document whose
                    # URL had a query string/fragment stripped by
                    # canonicalization, undercounting new_doc_ids (live
                    # audit evidence: new_docs=14 reported vs 88 actually
                    # processed for the same run).
                    db_doc = db.query(Document).filter(Document.url == canonicalize_url(norm["url"])).first()
                    if db_doc:
                        new_doc_ids.append(str(db_doc.id))
        except Exception as fe:
            log.warning("feed_fetch_failed", feed_name=feed.feed_name, error=str(fe))

    # Also pick up any PENDING docs from this client's feeds
    feed_urls = [f.feed_url for f in client_feeds]
    client_sources = db.query(Source).filter(Source.url.in_(feed_urls)).all()
    client_source_ids = [s.id for s in client_sources]

    if client_source_ids:
        pending_docs = db.query(Document).filter(
            Document.source_id.in_(client_source_ids),
            Document.processing_status == "PENDING"
        ).all()
        pending_ids = [str(d.id) for d in pending_docs]
        all_ids = list(set(new_doc_ids + pending_ids))
    else:
        all_ids = list(set(new_doc_ids))

    duration_ms = (time.perf_counter() - t0) * 1000
    log.info("stage_complete", new_docs=len(new_doc_ids), total_to_process=len(all_ids), duration_ms=round(duration_ms, 2))
    return all_ids


def _stage_process(ctx: PipelineContext, db, doc_ids: List[str]) -> None:
    """
    PROCESSING stage: run NLP pipeline on collected document IDs only.
    Never rescans the entire DB.
    """
    from app.models.document import Document
    from app.workers.intelligence_tasks import execute_document_intelligence_sync

    log = logger.bind(stage="PROCESSING", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started", doc_count=len(doc_ids))

    if not doc_ids:
        log.info("stage_skipped_no_documents")
        return

    # Mark documents as PROCESSING in bulk
    chunk_size = 100
    for i in range(0, len(doc_ids), chunk_size):
        chunk = doc_ids[i:i + chunk_size]
        db.query(Document).filter(Document.id.in_(chunk)).update(
            {"processing_status": "PROCESSING"}, synchronize_session=False
        )
    db.commit()

    # Item 17: PROCESSING is the stage that actually takes time (measured
    # live: 403s of a 431s run, 93.6% of total duration, ~4.6s/document of
    # transformer inference) but progress_pct sat pinned at 20 for the
    # entire stage, since nothing updated it between the COLLECTING->
    # PROCESSING transition (which sets 20) and the PROCESSING->TREND
    # transition (which sets 40). Update after every document: at ~4.6s/doc
    # the write is negligible overhead either way, so no batching interval
    # is needed. Capped at 39 (not 40) so an in-progress PROCESSING stage is
    # never visually indistinguishable from having already completed into
    # TREND, which is what the real _update_run(..., "TREND", ...) call
    # sets once this function returns.
    total = len(doc_ids)
    processed = 0
    failed = 0
    for doc_id in doc_ids:
        try:
            execute_document_intelligence_sync(doc_id, client_id=ctx.client_id)
            processed += 1
        except Exception as exc:
            failed += 1
            log.error("doc_nlp_failed", document_id=doc_id, error=str(exc))

        done = processed + failed
        pct = 20 + min(19, int(19 * done / total))
        _update_progress(db, ctx.run_id, pct, f"Processed {done}/{total} documents ({failed} failed)")

    duration_ms = (time.perf_counter() - t0) * 1000
    log.info("stage_complete", processed=processed, failed=failed, duration_ms=round(duration_ms, 2))


def _stage_trend(ctx: PipelineContext, db) -> None:
    log = logger.bind(stage="TREND", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started")
    TrendDetector().process_client(db, ctx.client_id, run_id=ctx.run_id, batch_id=ctx.run_id[:12])
    log.info("stage_complete", duration_ms=round((time.perf_counter() - t0) * 1000, 2))


def _stage_risk(ctx: PipelineContext, db) -> None:
    log = logger.bind(stage="RISK", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started")
    RiskEngine().process_client(db, ctx.client_id, run_id=ctx.run_id, batch_id=ctx.run_id[:12])
    log.info("stage_complete", duration_ms=round((time.perf_counter() - t0) * 1000, 2))


def _stage_alert(ctx: PipelineContext, db) -> None:
    from app.services.intelligence.alert_engine import AlertEngine as _AlertEngine
    log = logger.bind(stage="ALERT", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started")
    _AlertEngine().process_client(db, ctx.client_id, run_id=ctx.run_id, batch_id=ctx.run_id[:12])
    log.info("stage_complete", duration_ms=round((time.perf_counter() - t0) * 1000, 2))


def _stage_narrative(ctx: PipelineContext, db) -> None:
    from app.services.intelligence.narrative_engine import NarrativeEngine as _NarrativeEngine
    log = logger.bind(stage="NARRATIVE", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started")
    _NarrativeEngine().process_client(db, ctx.client_id, run_id=ctx.run_id, batch_id=ctx.run_id[:12])
    log.info("stage_complete", duration_ms=round((time.perf_counter() - t0) * 1000, 2))


def _stage_reputation(ctx: PipelineContext, db) -> None:
    from app.services.intelligence.reputation_engine import ReputationEngine as _ReputationEngine
    log = logger.bind(stage="REPUTATION", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started")
    _ReputationEngine().process_client(db, ctx.client_id, run_id=ctx.run_id, batch_id=ctx.run_id[:12])
    log.info("stage_complete", duration_ms=round((time.perf_counter() - t0) * 1000, 2))


def _stage_executive(ctx: PipelineContext, db) -> None:
    from app.services.intelligence.executive_reputation_engine import ExecutiveReputationEngine as _ExecEngine
    log = logger.bind(stage="EXECUTIVE", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started")
    _ExecEngine().process_client(db, ctx.client_id, run_id=ctx.run_id, batch_id=ctx.run_id[:12])
    log.info("stage_complete", duration_ms=round((time.perf_counter() - t0) * 1000, 2))


def _stage_benchmark(ctx: PipelineContext, db) -> None:
    from app.services.intelligence.benchmark_engine import BenchmarkEngine as _BenchmarkEngine
    log = logger.bind(stage="BENCHMARK", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    t0 = time.perf_counter()
    log.info("stage_started")
    _BenchmarkEngine().process_client(db, ctx.client_id, run_id=ctx.run_id, batch_id=ctx.run_id[:12])
    log.info("stage_complete", duration_ms=round((time.perf_counter() - t0) * 1000, 2))


def _stage_finalize(ctx: PipelineContext, db) -> None:
    """Final housekeeping stage before marking SUCCESS."""
    log = logger.bind(stage="FINALIZING", run_id=ctx.run_id, client_id=ctx.client_id, worker=ctx.worker_id)
    log.info("stage_started")
    db.commit()
    log.info("stage_complete")


# ---------------------------------------------------------------------------
# Stage task helpers (Phase 14)
# ---------------------------------------------------------------------------

def _load_context(db, run_id: str, client_id: str, worker_id: str) -> PipelineContext:
    """Rebuild the immutable per-stage context from the DB. Cheap (one PK
    lookup) — each stage now runs in its own process/task, so there is no
    single long-lived ctx to pass through anymore."""
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
    return PipelineContext(
        pipeline_run_id=str(pipeline_run.id) if pipeline_run else "",
        client_id=client_id,
        run_id=run_id,
        started_at=pipeline_run.started_at if pipeline_run else None,
        worker_id=worker_id,
        execution_mode="async",
        correlation_id=run_id,
    )


# ---------------------------------------------------------------------------
# Per-stage tasks — each is a real Celery task on the queue matching its
# resource profile, chained together by run_client_pipeline below. Every
# task raises on failure (no self.retry — matches Phase 13's single-attempt
# semantics) so Celery aborts the chain and fires the link_error callback.
# ---------------------------------------------------------------------------

@shared_task(bind=True, queue="io_queue", max_retries=0)
def pipeline_stage_collect(self, run_id: str, client_id: str, owner_id: str) -> List[str]:
    worker_id = f"worker-{os.getpid()}"
    log = logger.bind(run_id=run_id, client_id=client_id, worker_id=worker_id, task="pipeline_stage_collect")
    db = SessionLocal()
    try:
        ctx = _load_context(db, run_id, client_id, worker_id)
        if not _update_run(db, run_id, "COLLECTING", "Starting document collection"):
            log.warning("stage_skipped_stale_duplicate", stage="COLLECTING")
            db.commit()
            return []
        doc_ids = _stage_collect(ctx, db)

        # Collection itself is done here, but pipeline_stage_process
        # (nlp_queue, concurrency=3) may not actually start for a while if
        # every slot is busy -- transition into AWAITING_PROCESSING rather
        # than leaving the FSM pinned at COLLECTING for however long that
        # wait turns out to be. If this is a stale/duplicate call (fix
        # #1's redelivery guard), the transition itself is a harmless
        # no-op, but doc_ids is still real work already done and the chain
        # needs it regardless.
        if not _update_run(db, run_id, "AWAITING_PROCESSING", f"Collected {len(doc_ids)} documents"):
            log.warning("stage_skipped_stale_duplicate", stage="AWAITING_PROCESSING")

        run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).with_for_update().first()
        if run:
            run.current_worker = worker_id
        db.commit()
        return doc_ids
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@shared_task(bind=True, queue="nlp_queue", max_retries=0)
def pipeline_stage_process(self, doc_ids: List[str], run_id: str, client_id: str, owner_id: str) -> None:
    worker_id = f"worker-{os.getpid()}"
    log = logger.bind(run_id=run_id, client_id=client_id, worker_id=worker_id, task="pipeline_stage_process")
    db = SessionLocal()
    try:
        ctx = _load_context(db, run_id, client_id, worker_id)
        if not _update_run(db, run_id, "PROCESSING", f"Running NLP on {len(doc_ids)} documents"):
            log.warning("stage_skipped_stale_duplicate", stage="PROCESSING")
            db.commit()
            return
        _stage_process(ctx, db, doc_ids)
        run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).with_for_update().first()
        if run:
            run.current_worker = worker_id
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _make_aggregation_stage_task(stage_name: str, stage_fn, log_line: str, task_name: str):
    """
    Factory for the five identically-shaped aggregation stages (TREND, RISK,
    ALERT, NARRATIVE, REPUTATION, EXECUTIVE, BENCHMARK all follow the same
    pattern: load ctx, transition FSM, call the stage function, done). Avoids
    seven copy-pasted task bodies that all differ only in stage name/fn/log.
    """
    @shared_task(bind=True, queue="aggregation_queue", max_retries=0, name=task_name)
    def _task(self, run_id: str, client_id: str, owner_id: str) -> None:
        worker_id = f"worker-{os.getpid()}"
        log = logger.bind(run_id=run_id, client_id=client_id, worker_id=worker_id, task=task_name)
        db = SessionLocal()
        try:
            ctx = _load_context(db, run_id, client_id, worker_id)
            if not _update_run(db, run_id, stage_name, log_line):
                log.warning("stage_skipped_stale_duplicate", stage=stage_name)
                db.commit()
                return
            stage_fn(ctx, db)
            run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).with_for_update().first()
            if run:
                run.current_worker = worker_id
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return _task


pipeline_stage_trend = _make_aggregation_stage_task(
    "TREND", _stage_trend, "Running trend detection",
    "app.workers.aggregation_tasks.pipeline_stage_trend")
pipeline_stage_risk = _make_aggregation_stage_task(
    "RISK", _stage_risk, "Running risk engine",
    "app.workers.aggregation_tasks.pipeline_stage_risk")
pipeline_stage_alert = _make_aggregation_stage_task(
    "ALERT", _stage_alert, "Evaluating alerts",
    "app.workers.aggregation_tasks.pipeline_stage_alert")
pipeline_stage_narrative = _make_aggregation_stage_task(
    "NARRATIVE", _stage_narrative, "Generating narratives",
    "app.workers.aggregation_tasks.pipeline_stage_narrative")
pipeline_stage_reputation = _make_aggregation_stage_task(
    "REPUTATION", _stage_reputation, "Calculating reputation scores",
    "app.workers.aggregation_tasks.pipeline_stage_reputation")
pipeline_stage_executive = _make_aggregation_stage_task(
    "EXECUTIVE", _stage_executive, "Processing executive reputation",
    "app.workers.aggregation_tasks.pipeline_stage_executive")
pipeline_stage_benchmark = _make_aggregation_stage_task(
    "BENCHMARK", _stage_benchmark, "Running competitor benchmarks",
    "app.workers.aggregation_tasks.pipeline_stage_benchmark")


@shared_task(bind=True, queue="pipeline_queue", max_retries=0)
def pipeline_stage_finalize(self, run_id: str, client_id: str, owner_id: str) -> None:
    """
    Last link in the chain on success. Transitions FINALIZING → SUCCESS
    (PipelineRun.transition() computes duration_s/execution_duration_s
    automatically on entering a terminal state) and releases the lock —
    the one and only lock-release point on the success path.
    """
    from app.utils.redis_client import redis_client

    worker_id = f"worker-{os.getpid()}"
    log = logger.bind(run_id=run_id, client_id=client_id, worker_id=worker_id, task="pipeline_stage_finalize")
    db = SessionLocal()
    try:
        ctx = _load_context(db, run_id, client_id, worker_id)
        if not _update_run(db, run_id, "FINALIZING", "Finalizing pipeline run"):
            log.warning("stage_skipped_stale_duplicate", stage="FINALIZING")
            db.commit()
            return
        _stage_finalize(ctx, db)

        run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).with_for_update().first()
        if run:
            run.current_worker = worker_id
        db.commit()

        if not _update_run(db, run_id, "SUCCESS", "Pipeline completed"):
            log.warning("stage_skipped_stale_duplicate", stage="SUCCESS")
            db.commit()
            return
        db.commit()

        run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
        log.info("pipeline_task_succeeded",
                 execution_duration_s=run.execution_duration_s if run else None,
                 duration_s=run.duration_s if run else None)
    except Exception:
        db.rollback()
        raise
    finally:
        _release_lock(redis_client, client_id, owner_id, log)
        db.close()
        log.info("pipeline_task_finished")


@shared_task(queue="pipeline_queue")
def pipeline_stage_error_handler(request, exc, tb, run_id: str, client_id: str, owner_id: str) -> None:
    """
    Celery `link_error` callback, attached to every task in the chain via
    chain.apply_async(link_error=...). A chain aborts at the first failing
    task and never runs the rest, so this fires at most once per pipeline
    execution — the one and only lock-release point on the failure path.

    Celery calls error callbacks as (request, exc, traceback, *bound_args) —
    request/exc/tb describe whichever stage task actually failed; run_id/
    client_id/owner_id are the bound args passed via .s(...) at dispatch time.
    """
    from app.utils.redis_client import redis_client

    log = logger.bind(run_id=run_id, client_id=client_id, task="pipeline_stage_error_handler",
                       failed_celery_task_id=getattr(request, "id", "unknown"))
    error_detail = f"{exc!r}\n{tb}"
    log.error("pipeline_chain_stage_failed", error=str(exc))

    db = SessionLocal()
    try:
        _fail_run(db, run_id, error_detail, log)
    finally:
        _release_lock(redis_client, client_id, owner_id, log)
        db.close()
        log.info("pipeline_task_finished")


# ---------------------------------------------------------------------------
# Main pipeline task — lightweight orchestrator entry point (Phase 14)
# ---------------------------------------------------------------------------

@shared_task(bind=True, queue="pipeline_queue", max_retries=0, acks_late=True)
def run_client_pipeline(self, run_id: str, client_id: str):
    """
    Phase 14 Pipeline Orchestrator.

    Does no pipeline work itself. Acquires the per-client lock, builds a
    Celery chain of per-stage tasks (each on its own queue — see module
    docstring), dispatches it, and returns. celery-worker-pipeline's job is
    now just this: create/lock/dispatch, nothing CPU- or NLP-heavy.

    This task NEVER:
    - calls scheduler tasks
    - calls AsyncResult
    - spawns threads
    - uses heartbeat threads

    State is stored in PipelineRun (PostgreSQL) at each stage boundary,
    written by the stage tasks themselves. The API status endpoint reads
    only PipelineRun.

    Lock lifecycle:
        Acquire (SET NX) here → chain executes across queues →
        Release (compare-and-delete) in pipeline_stage_finalize (success)
        or pipeline_stage_error_handler (failure), or right here if the
        chain itself never made it to the broker. Exactly one of these
        three release points fires per run.
    """
    from app.utils.redis_client import redis_client

    worker_id = f"worker-{os.getpid()}"
    owner_id = f"{worker_id}-{uuid.uuid4().hex[:8]}"

    log = logger.bind(
        run_id=run_id,
        client_id=client_id,
        worker_id=worker_id,
        task="run_client_pipeline",
        celery_task_id=self.request.id or "unknown",
    )
    log.info("pipeline_orchestrator_started")

    # ── Load PipelineRun ───────────────────────────────────────────────────
    db = SessionLocal()
    try:
        pipeline_run = db.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
        if not pipeline_run:
            log.error("pipeline_run_not_found", run_id=run_id)
            return

        # Update worker assignment
        pipeline_run.current_worker = worker_id
        pipeline_run.celery_task_id = self.request.id or "unknown"
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("pipeline_run_load_failed", error=str(exc))
        db.close()
        return

    # ── Acquire distributed lock ───────────────────────────────────────────
    lock_acquired = _acquire_lock(redis_client, client_id, run_id, owner_id)
    if not lock_acquired:
        log.warning("pipeline_lock_already_held", client_id=client_id)
        _fail_run(db, run_id, "Pipeline lock already held by another run. Duplicate execution prevented.", log)
        db.close()
        return

    log.info("pipeline_lock_acquired", client_id=client_id)

    # Item 18: mark when execution actually begins (lock held, about to
    # dispatch stages), separately from started_at (set at row-creation/
    # QUEUED time, before this task was necessarily even picked up by a
    # worker) so execution_duration_s can be computed independent of queue
    # wait. This now covers the whole chain's wall-clock time, not just this
    # orchestrator task's — pipeline_stage_finalize reads it back via
    # PipelineRun.transition()'s automatic terminal-state computation.
    pipeline_run.processing_started_at = datetime.now(timezone.utc)
    db.commit()
    db.close()

    # ── Build and dispatch the stage chain ─────────────────────────────────
    # .s() for the two links that carry real data forward (doc_ids from
    # COLLECTING into PROCESSING); .si() (immutable) for every stage after
    # that, since they only need run_id/client_id/owner_id, not each other's
    # return values, and must ignore whatever the previous task returned.
    pipeline_chain = chain(
        pipeline_stage_collect.s(run_id, client_id, owner_id),
        pipeline_stage_process.s(run_id, client_id, owner_id),
        pipeline_stage_trend.si(run_id, client_id, owner_id),
        pipeline_stage_risk.si(run_id, client_id, owner_id),
        pipeline_stage_alert.si(run_id, client_id, owner_id),
        pipeline_stage_narrative.si(run_id, client_id, owner_id),
        pipeline_stage_reputation.si(run_id, client_id, owner_id),
        pipeline_stage_executive.si(run_id, client_id, owner_id),
        pipeline_stage_benchmark.si(run_id, client_id, owner_id),
        pipeline_stage_finalize.si(run_id, client_id, owner_id),
    )

    try:
        pipeline_chain.apply_async(
            link_error=pipeline_stage_error_handler.s(run_id, client_id, owner_id)
        )
        log.info("pipeline_chain_dispatched")
    except Exception as exc:
        # The chain never reached the broker (e.g. Redis unreachable at this
        # exact moment) -- no stage task exists to ever release the lock we
        # already hold, so release it here. This is the third and last of
        # the three mutually-exclusive release points.
        error_detail = f"Failed to dispatch pipeline stage chain: {exc}"
        log.error("pipeline_chain_dispatch_failed", error=str(exc), exc_info=True)
        fail_db = SessionLocal()
        try:
            _fail_run(fail_db, run_id, error_detail, log)
        finally:
            _release_lock(redis_client, client_id, owner_id, log)
            fail_db.close()
