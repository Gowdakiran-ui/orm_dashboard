"""Run Pipeline limits for client users: one run per client every PIPELINE_COOLDOWN_HOURS (default 6) and PIPELINE_MAX_RUNS_PER_DAY (default 3) in any
24 hours; a super admin is exempt; the 429 names the time of the next allowed run. In-memory SQLite, celery dispatch stubbed."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.db import Base
from app.models.client import Client
from app.models.pipeline_run import PipelineRun
import app.services.pipeline_service as ps
from app.services.pipeline_service import PipelineStartError, check_run_limits, start_pipeline_run

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)          # 14:30 IST


@compiles(PG_UUID, "sqlite")
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _jsonb(element, compiler, **kw):
    return "TEXT"


class _Task:
    id = "t"


class _Celery:
    class conf:
        broker_url = "memory://"

    def __init__(self):
        self.sent = []

    def send_task(self, name, args=None):
        self.sent.append(name)
        return _Task()


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    fake = _Celery()
    monkeypatch.setattr(ps, "celery_app", fake)
    monkeypatch.setattr(ps.settings, "MAX_CONCURRENT_PIPELINE_RUNS", 1)
    monkeypatch.setattr(ps.settings, "PIPELINE_COOLDOWN_HOURS", 6.0)
    monkeypatch.setattr(ps.settings, "PIPELINE_MAX_RUNS_PER_DAY", 3)
    yield db, fake
    db.close()


def _client(db, name="Godrej Properties"):
    c = Client(id=uuid.uuid4(), name=f"{name}-{uuid.uuid4().hex[:4]}")
    db.add(c)
    db.commit()
    return c


def _past_run(db, client, hours_ago, status="SUCCESS", error=None):
    started = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).replace(tzinfo=None)
    db.add(PipelineRun(client_id=str(client.id), run_id=uuid.uuid4().hex, status=status, stage=status, progress_pct=100, execution_mode="async",
                       started_at=started, error_detail=error))
    db.commit()


def _refusal(db, client):
    with pytest.raises(PipelineStartError) as e:
        start_pipeline_run(db, client.id, enforce_limits=True)
    return e.value


# ---- defaults and configuration ------------------------------------------------------------------------------------------------------------
def test_defaults_are_six_hours_and_three_a_day_and_read_from_the_environment(monkeypatch):
    s = Settings(_env_file=None)
    assert s.PIPELINE_COOLDOWN_HOURS == 6.0 and s.PIPELINE_MAX_RUNS_PER_DAY == 3
    monkeypatch.setenv("PIPELINE_COOLDOWN_HOURS", "2.5")
    monkeypatch.setenv("PIPELINE_MAX_RUNS_PER_DAY", "5")
    s2 = Settings(_env_file=None)
    assert s2.PIPELINE_COOLDOWN_HOURS == 2.5 and s2.PIPELINE_MAX_RUNS_PER_DAY == 5


# ---- the cooldown -----------------------------------------------------------------------------------------------------------------------------
def test_first_run_is_allowed_and_an_immediate_second_run_is_refused_with_the_next_time(env):
    db, fake = env
    c = _client(db)
    first = start_pipeline_run(db, c.id, enforce_limits=True)
    assert first["status"] == "QUEUED"
    run = db.query(PipelineRun).filter(PipelineRun.run_id == first["run_id"]).one()
    run.status = run.stage = "SUCCESS"                      # finished: the plain 409 no longer applies, only the limit does
    db.commit()
    err = _refusal(db, c)
    assert err.status_code == 429 and "one run every 6 hours" in err.detail
    assert "The last run started" in err.detail and "IST" in err.detail and "The next run is allowed from" in err.detail
    assert "Ask your administrator" in err.detail
    assert 5 * 3600 < err.retry_after_s <= 6 * 3600 and len(fake.sent) == 1


def test_allowed_again_after_six_hours(env):
    db, fake = env
    c = _client(db)
    _past_run(db, c, 6.1)
    assert start_pipeline_run(db, c.id, enforce_limits=True)["status"] == "QUEUED"
    c2 = _client(db)
    _past_run(db, c2, 5.9)
    assert _refusal(db, c2).status_code == 429


def test_the_message_gives_the_exact_next_time_in_ist_and_the_wait():
    # last run 02:30 UTC = 08:00 IST; next allowed 14:30 IST (6 h later); "now" is 09:00 UTC = 14:30 IST -> that is the boundary, so move now back
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    c = Client(id=uuid.uuid4(), name="Godrej Properties")
    db.add(c)
    db.commit()
    db.add(PipelineRun(client_id=str(c.id), run_id="r1", status="SUCCESS", stage="SUCCESS", progress_pct=100, execution_mode="async",
                       started_at=datetime(2026, 11, 10, 6, 30)))        # 12:00 IST
    db.commit()
    err = check_run_limits(db, c.id, now=NOW)                            # now = 14:30 IST; next allowed = 18:00 IST
    assert err.status_code == 429
    assert "Run limit for Godrej Properties: one run every 6 hours." in err.detail
    assert "The last run started 10-11-2026, 12:00 PM IST." in err.detail
    assert "The next run is allowed from 10-11-2026, 06:00 PM IST (in 3 h 30 min)." in err.detail
    assert err.retry_after_s == 3 * 3600 + 1800
    db.close()


# ---- the daily limit ----------------------------------------------------------------------------------------------------------------------------
def test_three_runs_in_24_hours_block_the_fourth_until_the_oldest_ages_out(env):
    db, fake = env
    c = _client(db)
    for h in (20, 13, 7):                                   # each more than 6 hours after the one before; all inside 24 hours
        _past_run(db, c, h)
    err = _refusal(db, c)
    assert err.status_code == 429 and "at most 3 runs a day" in err.detail and "one run every" not in err.detail
    assert 3.9 * 3600 < err.retry_after_s < 4.1 * 3600      # the 20-hour-old run leaves the window in 4 hours
    assert len(fake.sent) == 0


def test_when_both_limits_apply_the_later_time_is_named(env):
    db, fake = env
    c = _client(db)
    for h in (23, 11, 1):
        _past_run(db, c, h)                                  # cooldown ends in 5 h; the daily window frees up in 1 h -> 5 h is the later one
    err = _refusal(db, c)
    assert "one run every 6 hours and at most 3 runs a day" in err.detail
    assert 4.9 * 3600 < err.retry_after_s < 5.1 * 3600


def test_a_run_older_than_24_hours_does_not_count(env):
    db, fake = env
    c = _client(db)
    for h in (30, 27, 25):
        _past_run(db, c, h)
    assert start_pipeline_run(db, c.id, enforce_limits=True)["status"] == "QUEUED"


# ---- who is limited -------------------------------------------------------------------------------------------------------------------------------
def test_the_limits_are_per_client(env):
    db, fake = env
    a, b = _client(db, "A"), _client(db, "B")
    _past_run(db, a, 1)
    assert _refusal(db, a).status_code == 429
    assert start_pipeline_run(db, b.id, enforce_limits=True)["status"] == "QUEUED"


def test_without_enforce_limits_nothing_changes_the_admin_path(env):
    db, fake = env
    c = _client(db)
    _past_run(db, c, 0.5)
    assert start_pipeline_run(db, c.id)["status"] == "QUEUED"        # the admin CLI and a super admin


def test_endpoint_applies_the_limits_to_a_client_user_and_not_to_a_super_admin(env):
    from app.api.endpoints.clients import trigger_client_pipeline
    db, fake = env
    c = _client(db)
    _past_run(db, c, 1)
    handler = getattr(trigger_client_pipeline, "__wrapped__", trigger_client_pipeline)
    with pytest.raises(HTTPException) as e:
        handler(request=None, response=None, client_id=c.id, db=db, _access=None, current_user=SimpleNamespace(role="client_user"))
    assert e.value.status_code == 429 and "The next run is allowed from" in e.value.detail
    assert int(e.value.headers["Retry-After"]) > 4 * 3600
    ok = handler(request=None, response=None, client_id=c.id, db=db, _access=None, current_user=SimpleNamespace(role="super_admin"))
    assert ok["status"] == "QUEUED"
    # the super admin's run is itself a run of the client: it uses up the client's cooldown for client users
    r = db.query(PipelineRun).filter(PipelineRun.run_id == ok["run_id"]).one()
    r.status = r.stage = "SUCCESS"
    db.commit()
    with pytest.raises(HTTPException) as e2:
        handler(request=None, response=None, client_id=c.id, db=db, _access=None, current_user=SimpleNamespace(role="client_user"))
    assert e2.value.status_code == 429


def test_an_active_run_for_the_client_still_gets_the_plain_409_first(env):
    db, fake = env
    c = _client(db)
    start_pipeline_run(db, c.id, enforce_limits=True)
    err = _refusal(db, c)
    assert err.status_code == 409 and "already active" in err.detail


# ---- configuration switches ---------------------------------------------------------------------------------------------------------------------
def test_limits_can_be_changed_or_switched_off(env, monkeypatch):
    db, fake = env
    c = _client(db)
    _past_run(db, c, 1)
    monkeypatch.setattr(ps.settings, "PIPELINE_COOLDOWN_HOURS", 0)                 # cooldown off; the daily limit (3) is not reached by one run
    assert check_run_limits(db, c.id) is None
    monkeypatch.setattr(ps.settings, "PIPELINE_COOLDOWN_HOURS", 0.5)
    assert check_run_limits(db, c.id) is None                                       # 1 hour ago is past a 30-minute cooldown
    monkeypatch.setattr(ps.settings, "PIPELINE_COOLDOWN_HOURS", 6)
    monkeypatch.setattr(ps.settings, "PIPELINE_MAX_RUNS_PER_DAY", 1)
    monkeypatch.setattr(ps.settings, "PIPELINE_COOLDOWN_HOURS", 0)
    assert "at most 1 runs a day" in check_run_limits(db, c.id).detail
    monkeypatch.setattr(ps.settings, "PIPELINE_MAX_RUNS_PER_DAY", 0)
    assert check_run_limits(db, c.id) is None                                       # both off


def test_a_run_that_never_started_because_the_broker_was_down_does_not_count(env):
    db, fake = env
    c = _client(db)
    _past_run(db, c, 0.2, status="FAILED", error="Failed to dispatch pipeline task: broker down")
    assert start_pipeline_run(db, c.id, enforce_limits=True)["status"] == "QUEUED"
    c2 = _client(db)
    _past_run(db, c2, 0.2, status="FAILED", error="Stage collect failed")        # a run that really ran and failed does count
    assert _refusal(db, c2).status_code == 429
