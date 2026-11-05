"""The two pages' API for seeded entities: GET /seeded, the additive fields on /executives and /benchmark, and
competitor-search as a POST. In-memory SQLite, dummy DATABASE_URL, no network."""
import os
import sys
import uuid
import datetime as dt
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.document import Document
from app.models.executive_reputation import ExecutiveReputationScore
from app.models.seeded_entity import SeededEntity
import app.api.endpoints.client_intelligence as ci


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _setup(db):
    c = Client(id=uuid.uuid4(), name="Godrej Properties")
    db.add(c)
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name="Godrej Properties", entity_type="brand")
    chair = Entity(id=uuid.uuid4(), client_id=c.id, name="Pirojsha Godrej", entity_type="person")
    cfo = Entity(id=uuid.uuid4(), client_id=c.id, name="Rajendra Khetawat", entity_type="person")
    old = Entity(id=uuid.uuid4(), client_id=c.id, name="Geetika Trehan", entity_type="person")
    dlf = Entity(id=uuid.uuid4(), client_id=c.id, name="DLF", entity_type="competitor")
    db.add_all([brand, chair, cfo, old, dlf])
    db.commit()
    # chair co-occurs with the brand; the CFO has no document at all; Geetika has none with the brand
    d = Document(id=uuid.uuid4(), url="http://t.test/1", title="Pirojsha Godrej of Godrej Properties", normalized_content="x", published_at=dt.datetime.now(dt.timezone.utc))
    db.add(d)
    db.flush()
    db.add_all([EntityMention(document_id=d.id, entity_id=chair.id, mention_count=1), EntityMention(document_id=d.id, entity_id=brand.id, mention_count=1)])
    now = dt.datetime.now(dt.timezone.utc)
    for ent, window in ((chair, 365), (cfo, None), (old, None)):
        raw = {"document_count": 1}
        if window:
            raw["window_days"] = window
        db.add(ExecutiveReputationScore(client_id=c.id, entity_id=ent.id, executive_name=ent.name, score=70.0, grade="B", sentiment_component=1.0,
                                        risk_component=1.0, visibility_component=1.0, confidence_score=0.5, created_at=now,
                                        calculation_lineage={"raw_values": raw}, health_status="COMPLETE"))
    db.add_all([
        SeededEntity(client_id=c.id, entity_id=cfo.id, kind="executive", name="Rajendra Khetawat", rank=3, role="CFO", validated=True, status="active"),
        SeededEntity(client_id=c.id, entity_id=chair.id, kind="executive", name="Pirojsha Godrej", rank=1, role="Chairperson", validated=True, status="active"),
        SeededEntity(client_id=c.id, entity_id=dlf.id, kind="competitor", name="DLF", rank=1, context_term="real estate", validated=True, status="active"),
        SeededEntity(client_id=c.id, entity_id=None, kind="executive", name="Needs Review", rank=2, validated=False, status="needs_review"),
    ])
    db.commit()
    return c, chair, cfo, old, dlf


def test_seeded_endpoint_lists_only_active_rows_in_order_with_the_windows(db):
    c, chair, cfo, old, dlf = _setup(db)
    out = ci.get_client_seeded(c.id, db)
    assert out["window"] == {"executive_days": 365, "benchmark_days": 90}
    assert [e["name"] for e in out["executives"]] == ["Pirojsha Godrej", "Rajendra Khetawat"]
    assert [e["role"] for e in out["executives"]] == ["Chairperson", "CFO"]
    assert [e["name"] for e in out["competitors"]] == ["DLF"] and out["competitors"][0]["context_term"] == "real estate"
    assert all(e["entity_id"] for e in out["executives"])                      # needs_review rows (no entity) are never listed


def test_seeded_endpoint_is_empty_before_seeding(db):
    c = Client(id=uuid.uuid4(), name="X")
    db.add(c)
    db.commit()
    out = ci.get_client_seeded(c.id, db)
    assert out["executives"] == [] and out["competitors"] == []


def test_executives_payload_marks_seeded_people_and_keeps_a_seeded_person_without_brand_cooccurrence(db):
    c, chair, cfo, old, dlf = _setup(db)
    rows = {r["name"]: r for r in ci.get_client_executives(c.id, db)}
    assert rows["Pirojsha Godrej"]["seeded"] and rows["Pirojsha Godrej"]["seed_rank"] == 1 and rows["Pirojsha Godrej"]["seed_role"] == "Chairperson"
    assert rows["Pirojsha Godrej"]["window_days"] == 365
    # the CFO has no document with the brand, but is seeded, so the brand gate does not hide the row
    assert "Rajendra Khetawat" in rows and rows["Rajendra Khetawat"]["seeded"] and rows["Rajendra Khetawat"]["window_days"] == 30   # row stored before the setting
    # a non-seeded person with no brand co-occurrence is still hidden, exactly as before
    assert "Geetika Trehan" not in rows


def _bm(entity_id, rank, name, sov=1.0, rep=70.0, window=None):
    meta = {"mentions_30d": 8}
    if window:
        meta["window_days"] = window
    b = SimpleNamespace(id=uuid.uuid4(), competitor_entity_id=entity_id, rank=rank, share_of_voice=sov, reputation_score=rep, sentiment_score=0.0,
                        risk_score=0.0, visibility_score=8.0, health_status="COMPLETE", confidence_score=0.5, data_coverage=0.5,
                        evidence_metadata=meta, created_at=dt.datetime.now(dt.timezone.utc))
    return (b, SimpleNamespace(name=name))


def test_benchmark_rows_carry_window_and_seed_fields_and_seeded_competitors_come_first():
    a, b, c_ = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [_bm(a, 1, "Lodha"), _bm(b, 2, "DLF", window=90), _bm(c_, 3, "Prestige", window=90)]
    out = ci._build_benchmark_response(rows, 75.0, 25, 0, None, seed_ranks={c_: 1, b: 2})
    assert [r["competitor_name"] for r in out] == ["Prestige", "DLF", "Lodha"]          # seed order, then "also tracked"
    assert [r["seeded"] for r in out] == [True, True, False] and [r["seed_rank"] for r in out] == [1, 2, None]
    assert [r["window_days"] for r in out] == [90, 90, 30]                              # an old row stored without the setting used 30 days
    plain = ci._build_benchmark_response(rows, 75.0, 25, 0, None)
    assert [r["competitor_name"] for r in plain] == ["Lodha", "DLF", "Prestige"] and not any(r["seeded"] for r in plain)


def test_competitor_search_is_a_post_not_a_get():
    methods = {m for r in ci.router.routes if r.path.endswith("/competitor-search") for m in r.methods}
    assert methods == {"POST"}


def test_seeded_refresh_is_super_admin_only():
    route = next(r for r in ci.router.routes if r.path.endswith("/seeded/refresh"))
    assert route.methods == {"POST"}
    deps = [d.call.__name__ for d in route.dependant.dependencies]
    assert "require_super_admin" in deps
