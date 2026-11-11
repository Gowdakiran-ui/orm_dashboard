"""GET /clients/ carries last_successful_run_at so the dashboard can open on the most recently refreshed client.
The list order (by name) is unchanged. In-memory SQLite."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.client import Client
from app.models.pipeline_run import PipelineRun
from app.schemas.client import ClientResponse
from app.services.client_service import attach_last_successful_run, get_clients


@compiles(PG_UUID, "sqlite")
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _jsonb(element, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _run(db, client, days_ago, status="SUCCESS"):
    t = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(tzinfo=None)
    db.add(PipelineRun(client_id=str(client.id), run_id=uuid.uuid4().hex, status=status, stage=status, progress_pct=100,
                       execution_mode="async", started_at=t, finished_at=t))
    db.commit()


def test_latest_success_per_client_failed_and_missing_runs_are_none_and_order_is_by_name(db):
    adani, easemytrip, godrej = (Client(id=uuid.uuid4(), name=n) for n in ("Adani Group", "EaseMyTrip", "Godrej Properties"))
    db.add_all([adani, easemytrip, godrej])
    db.commit()
    _run(db, adani, 30)
    _run(db, godrej, 9)
    _run(db, godrej, 2)
    _run(db, easemytrip, 1, status="FAILED")          # a failed run does not count
    out = attach_last_successful_run(db, get_clients(db))
    assert [c.name for c in out] == ["Adani Group", "EaseMyTrip", "Godrej Properties"]
    by = {c.name: c.last_successful_run_at for c in out}
    assert by["EaseMyTrip"] is None
    assert by["Godrej Properties"] > by["Adani Group"]
    payload = [ClientResponse.model_validate(c).model_dump() for c in out]
    assert payload[2]["last_successful_run_at"] == by["Godrej Properties"] and payload[1]["last_successful_run_at"] is None


def test_empty_list_is_fine(db):
    assert attach_last_successful_run(db, []) == []
