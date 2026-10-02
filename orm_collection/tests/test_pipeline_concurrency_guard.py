"""Pipeline start: the concurrency guard (decision D4, 2026-10-03), stale-run handling, and endpoint/CLI parity.
In-memory SQLite, DATABASE_URL forced to an unreachable dummy, celery dispatch stubbed: nothing here touches Redis or a real database."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.client import Client
from app.models.pipeline_run import PipelineRun
import app.services.pipeline_service as ps
from app.services.pipeline_service import CONCURRENCY_MESSAGE, PipelineStartError, start_pipeline_run


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


class _Task:
    id = "task-1"


class _FakeCelery:
    class conf:
        broker_url = "memory://"

    def __init__(self):
        self.sent = []
        self.fail = False

    def send_task(self, name, args=None):
        if self.fail:
            raise RuntimeError("broker down")
        self.sent.append((name, args))
        return _Task()


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    fake = _FakeCelery()
    monkeypatch.setattr(ps, "celery_app", fake)
    monkeypatch.setattr(ps.settings, "MAX_CONCURRENT_PIPELINE_RUNS", 1)
    yield db, fake
    db.close()


def _client(db, name):
    c = Client(id=uuid.uuid4(), name=f"{name}-{uuid.uuid4().hex[:5]}")
    db.add(c)
    db.commit()
    return c.id


def _run(db, client_id, status="PROCESSING", minutes_ago=5):
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    r = PipelineRun(client_id=str(client_id), run_id=uuid.uuid4().hex, status=status, stage=status, progress_pct=20, execution_mode="async",
                    started_at=started.replace(tzinfo=None))
    db.add(r)
    db.commit()
    return r


def test_second_client_is_refused_while_another_client_runs(env):
    db, fake = env
    a, b = _client(db, "A"), _client(db, "B")
    _run(db, a, "PROCESSING")
    with pytest.raises(PipelineStartError) as e:
        start_pipeline_run(db, b)
    assert e.value.status_code == 409 and e.value.detail == CONCURRENCY_MESSAGE == "Another client's pipeline is running. Try again when it finishes."
    assert fake.sent == [] and db.query(PipelineRun).count() == 1          # nothing created, nothing dispatched


def test_same_client_keeps_the_original_duplicate_message(env):
    db, _ = env
    a = _client(db, "A")
    r = _run(db, a, "RISK")
    with pytest.raises(PipelineStartError) as e:
        start_pipeline_run(db, a)
    assert e.value.status_code == 409 and e.value.detail.startswith("Pipeline already active for this client") and r.run_id in e.value.detail


@pytest.mark.parametrize("status", ["QUEUED", "COLLECTING", "AWAITING_PROCESSING", "PROCESSING", "RISK", "ALERT", "AI_SUMMARY", "REPUTATION", "EXECUTIVE", "BENCHMARK", "FINALIZING"])
def test_every_non_terminal_status_blocks_including_awaiting_processing(env, status):
    db, _ = env
    a, b = _client(db, "A"), _client(db, "B")
    _run(db, a, status)
    assert ps.check_can_start(db, b) is not None


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED"])
def test_allowed_after_the_other_run_finishes(env, status):
    db, fake = env
    a, b = _client(db, "A"), _client(db, "B")
    _run(db, a, status)
    out = start_pipeline_run(db, b)
    assert out["status"] == "QUEUED" and fake.sent == [("app.workers.aggregation_tasks.run_client_pipeline", [out["run_id"], str(b)])]


def test_a_stuck_run_older_than_the_watchdog_timeout_does_not_block(env):
    db, _ = env
    a, b = _client(db, "A"), _client(db, "B")
    _run(db, a, "PROCESSING", minutes_ago=ps.PIPELINE_RUN_STALE_MINUTES + 10)
    assert ps.check_can_start(db, b) is None and ps.check_can_start(db, a) is None     # neither another client nor the same client is blocked forever
    _run(db, b, "PROCESSING", minutes_ago=ps.PIPELINE_RUN_STALE_MINUTES - 10)           # a run just inside the window still blocks
    assert ps.check_can_start(db, a) is not None


def test_stale_threshold_equals_the_watchdog_threshold():
    from app.workers.aggregation_tasks import _PIPELINE_RUN_TIMEOUT_MINUTES
    assert ps.PIPELINE_RUN_STALE_MINUTES == _PIPELINE_RUN_TIMEOUT_MINUTES


def test_the_limit_is_configurable(env, monkeypatch):
    db, _ = env
    a, b, c = _client(db, "A"), _client(db, "B"), _client(db, "C")
    _run(db, a, "PROCESSING")
    monkeypatch.setattr(ps.settings, "MAX_CONCURRENT_PIPELINE_RUNS", 2)
    start_pipeline_run(db, b)                                   # second concurrent run allowed at 2
    with pytest.raises(PipelineStartError):
        start_pipeline_run(db, c)                               # third is not


def test_unknown_client_is_404(env):
    db, _ = env
    with pytest.raises(PipelineStartError) as e:
        start_pipeline_run(db, uuid.uuid4())
    assert e.value.status_code == 404


def test_dispatch_failure_marks_the_run_failed_and_is_503(env, monkeypatch):
    db, fake = env
    a = _client(db, "A")

    def _transition(self, stage, log_line=None):   # SQLite returns naive datetimes, which the real transition() cannot subtract; Postgres keeps tz
        self.status = self.stage = stage
        self.log_tail = log_line

    monkeypatch.setattr(PipelineRun, "transition", _transition)
    fake.fail = True
    with pytest.raises(PipelineStartError) as e:
        start_pipeline_run(db, a)
    assert e.value.status_code == 503
    run = db.query(PipelineRun).one()
    assert run.status == "FAILED" and "Failed to dispatch" in (run.error_detail or "")
    fake.fail = False
    assert start_pipeline_run(db, a)["status"] == "QUEUED"      # a failed run does not block a retry


def test_endpoint_and_service_create_identical_queued_runs_and_endpoint_maps_refusals(env):
    from app.api.endpoints.clients import trigger_client_pipeline
    db, fake = env
    a, b = _client(db, "A"), _client(db, "B")
    handler = getattr(trigger_client_pipeline, "__wrapped__", trigger_client_pipeline)
    via_endpoint = handler(request=None, response=None, client_id=a, db=db, _access=None)
    ra = db.query(PipelineRun).filter(PipelineRun.run_id == via_endpoint["run_id"]).one()
    ra.status = ra.stage = "SUCCESS"
    db.commit()
    via_service = start_pipeline_run(db, b)
    assert set(via_endpoint) == set(via_service)
    assert {k: via_endpoint[k] for k in ("status", "stage", "progress_pct", "message")} == {k: via_service[k] for k in ("status", "stage", "progress_pct", "message")}
    rb = db.query(PipelineRun).filter(PipelineRun.run_id == via_service["run_id"]).one()
    assert (ra.execution_mode, rb.execution_mode) == ("async", "async") and rb.status == "QUEUED" and rb.progress_pct == 0
    assert [n for n, _ in fake.sent] == ["app.workers.aggregation_tasks.run_client_pipeline"] * 2
    with pytest.raises(HTTPException) as e:                      # b is now active; a new run for a is refused with the plain message
        handler(request=None, response=None, client_id=a, db=db, _access=None)
    assert e.value.status_code == 409 and e.value.detail == CONCURRENCY_MESSAGE


def test_admin_cli_uses_the_same_service_function():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = open(os.path.join(root, "scripts", "run_pipeline.py"), encoding="utf-8").read()
    assert "from app.services.pipeline_service import" in src and "start_pipeline_run(db, client_id)" in src
    assert "--start" in src and "celery_app" not in src          # it never dispatches by itself
