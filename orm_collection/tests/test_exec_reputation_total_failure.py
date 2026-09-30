"""
Total-failure visibility for ExecutiveReputationEngine.

Every per-executive failure is isolated in its own savepoint and only logged.
That let a 100% failure rate (executive_reputation_scores.narrative_component
NOT NULL violation) look like a successful pipeline run for 15 days. With
raise_on_total_failure=True (used only by the pipeline's EXECUTIVE stage) a run
where EVERY evaluated executive fails now raises; partial failures never do.

Uses an in-memory SQLite session and patches _evaluate_single_executive_optimized,
so nothing here touches the real database.
"""
import os
import sys
import uuid

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity
from app.services.intelligence.executive_reputation_engine import (
    ExecutiveReputationEngine,
    ExecutiveReputationTotalFailure,
)


@compiles(PG_UUID, 'sqlite')
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, 'sqlite')
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


_engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(_engine)
Session = sessionmaker(bind=_engine)


def _client_with_executives(db, n):
    client_id = uuid.uuid4()
    db.add(Client(id=client_id, name=f"Client {client_id.hex[:6]}"))
    for i in range(n):
        db.add(Entity(id=uuid.uuid4(), client_id=client_id, name=f"Exec {i}", entity_type="person"))
    db.commit()
    return client_id


def _patch_evaluate(monkeypatch, fail_names):
    def fake(self, db, client_id, exec_entity, *a, **kw):
        if exec_entity.name in fail_names:
            raise RuntimeError("simulated NotNullViolation")
    monkeypatch.setattr(ExecutiveReputationEngine, "_evaluate_single_executive_optimized", fake)


def test_total_failure_raises_when_opted_in(monkeypatch):
    db = Session()
    try:
        cid = _client_with_executives(db, 3)
        _patch_evaluate(monkeypatch, {"Exec 0", "Exec 1", "Exec 2"})
        with pytest.raises(ExecutiveReputationTotalFailure) as exc:
            ExecutiveReputationEngine().process_client(db, cid, raise_on_total_failure=True)
        assert "all 3/3" in str(exc.value)
        assert "simulated NotNullViolation" in str(exc.value)
    finally:
        db.close()


def test_total_failure_does_not_raise_by_default(monkeypatch):
    """Other callers (executive search endpoint, promotion path) keep today's behavior."""
    db = Session()
    try:
        cid = _client_with_executives(db, 3)
        _patch_evaluate(monkeypatch, {"Exec 0", "Exec 1", "Exec 2"})
        ExecutiveReputationEngine().process_client(db, cid)  # must not raise
    finally:
        db.close()


def test_partial_failure_never_raises(monkeypatch):
    db = Session()
    try:
        cid = _client_with_executives(db, 3)
        _patch_evaluate(monkeypatch, {"Exec 1"})
        ExecutiveReputationEngine().process_client(db, cid, raise_on_total_failure=True)
    finally:
        db.close()


def test_no_executives_does_not_raise(monkeypatch):
    db = Session()
    try:
        cid = _client_with_executives(db, 0)
        _patch_evaluate(monkeypatch, set())
        ExecutiveReputationEngine().process_client(db, cid, raise_on_total_failure=True)
    finally:
        db.close()
