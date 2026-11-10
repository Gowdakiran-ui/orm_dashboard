"""Intelligence Stream: flagged articles first. GET /documents/client/{id}?flagged_only=true returns the client's documents above the LOW band,
strongest first then newest first, however old they are; the default list (newest first, capped at 500) is unchanged because the charts and the
AI-summary sweep read it. In-memory SQLite only."""
import datetime
import os
import sys
import uuid

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
from app.models.document import Document, DocumentMatch
from app.models.entity import Entity
from app.models.risk import RiskEvent
import app.api.endpoints.documents as docs_ep

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 10, tzinfo=UTC)


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
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _world(db, name="Acme"):
    c = Client(id=uuid.uuid4(), name=name)
    db.add(c)
    db.commit()
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name="Acme", entity_type="brand")
    comp = Entity(id=uuid.uuid4(), client_id=c.id, name="Rival", entity_type="competitor")
    db.add_all([brand, comp])
    db.commit()
    return c, brand, comp


def _doc(db, brand, title, days_ago, score=None, other=None):
    d = Document(id=uuid.uuid4(), url=f"http://t/{uuid.uuid4()}", normalized_content="x", title=title, published_at=NOW - datetime.timedelta(days=days_ago))
    db.add(d)
    db.add(DocumentMatch(document_id=d.id, matched_entity_id=brand.id))
    db.commit()
    for ent, sc in ([(brand, score)] if score is not None else []) + ([other] if other else []):
        db.add(RiskEvent(client_id=brand.client_id, document_id=d.id, entity_id=ent.id, risk_score=sc, risk_level="X", explainability={}))
    db.commit()
    return d


def test_flagged_first_then_newest_even_when_the_flagged_ones_are_old(db):
    c, brand, comp = _world(db)
    low_new = [_doc(db, brand, f"low {i}", i, score=0.0) for i in range(1, 6)]
    old_high = _doc(db, brand, "old high", 400, score=51.0)
    old_critical = _doc(db, brand, "old critical", 700, score=80.0)
    mid_recent = _doc(db, brand, "recent medium", 3, score=30.0)
    mid_older = _doc(db, brand, "older medium", 40, score=30.0)
    got = docs_ep.get_client_flagged_documents(db, c.id)
    assert [d.title for d in got] == ["old critical", "old high", "recent medium", "older medium"]       # score desc, then date desc
    assert not {d.id for d in got} & {d.id for d in low_new}                                              # LOW items are not flagged


def test_a_competitors_score_does_not_flag_the_clients_document(db):
    c, brand, comp = _world(db)
    only_comp = _doc(db, brand, "rival raided", 5, score=0.0, other=(comp, 90.0))
    own = _doc(db, brand, "own high", 6, score=60.0, other=(comp, 95.0))
    got = docs_ep.get_client_flagged_documents(db, c.id)
    assert [d.title for d in got] == ["own high"]                              # the document counts once, at the client's own best score


def test_document_without_any_risk_event_and_documents_of_other_clients_are_not_listed(db):
    c, brand, comp = _world(db)
    _doc(db, brand, "unscored", 2, score=None)
    other_client, other_brand, _ = _world(db, "Other Co")
    _doc(db, other_brand, "someone else's", 2, score=70.0)
    assert docs_ep.get_client_flagged_documents(db, c.id) == []
    assert [d.title for d in docs_ep.get_client_flagged_documents(db, other_client.id)] == ["someone else's"]


def test_limit_and_the_endpoint_flag(db):
    c, brand, comp = _world(db)
    for i in range(7):
        _doc(db, brand, f"flag {i}", i, score=40.0 + i)
    assert [d.title for d in docs_ep.get_client_flagged_documents(db, c.id, limit=3)] == ["flag 6", "flag 5", "flag 4"]
    out = docs_ep.read_client_documents(c.id, 0, 100, True, db)
    assert [d["title"] for d in out][:2] == ["flag 6", "flag 5"] and len(out) == 7
    page2 = docs_ep.read_client_documents(c.id, 2, 3, True, db)
    assert [d["title"] for d in page2] == ["flag 4", "flag 3", "flag 2"]
    assert all(d["risk_level"] in ("MEDIUM", "HIGH", "CRITICAL", "LOW") for d in out)


def test_default_list_is_still_newest_first_and_ignores_risk(db):
    c, brand, comp = _world(db)
    _doc(db, brand, "old critical", 700, score=80.0)
    for i in range(1, 4):
        _doc(db, brand, f"new low {i}", i, score=0.0)
    out = docs_ep.read_client_documents(c.id, 0, 100, False, db)
    assert [d["title"] for d in out] == ["new low 1", "new low 2", "new low 3", "old critical"]
    assert [d.title for d in docs_ep.get_client_visible_documents(db, c.id, limit=2)] == ["new low 1", "new low 2"]
