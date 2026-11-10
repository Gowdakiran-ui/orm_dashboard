"""Benchmark view: an unseeded competitor that is the same company as a seeded one is hidden (entity kept). In-memory SQLite only."""
import os
import sys
import uuid

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.api.endpoints.client_intelligence as ci
from app.core.db import Base
from app.models.client import Client
from app.models.competitor_benchmark import CompetitorBenchmark
from app.models.entity import Entity
from app.models.seeded_entity import SeededEntity
from app.services.intelligence.competitor_dupes import duplicate_groups, hidden_duplicates, name_key


@compiles(PG_UUID, "sqlite")
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _jsonb(element, compiler, **kw):
    return "TEXT"


@pytest.mark.parametrize("a,b,same", [
    ("Prestige Group", "Prestige Estates", True),
    ("Prestige Group", "Prestige Estates Projects Limited", False),          # "projects" is not a generic word: a different name
    ("DLF", "DLF Limited", True),
    ("Lodha", "Lodha Group India", True),
    ("Mahindra Lifespace Developers", "Mahindra Lifespaces Developers", True),
    ("Tata Projects", "Tata Motors", False),
    ("Oberoi Realty", "Oberoi Realty Ltd.", True),
    ("Emaar", "Emaar India", True),
    ("Banke International Properties", "Prestige Estates", False),
    ("Godrej Properties", "Godrej Industries", False),
])
def test_name_key_matches_the_same_company_only(a, b, same):
    assert (name_key(a) == name_key(b)) is same


def test_name_key_edge_cases():
    assert name_key("") == () and name_key(None) == () and name_key("The Group Ltd") == ()
    assert name_key("Prestige Group") == ("prestige",) and name_key("PRESTIGE   estates") == ("prestige",)


def test_only_unseeded_duplicates_of_a_seeded_competitor_are_hidden():
    a, b, c, d, e = (uuid.uuid4() for _ in range(5))
    pairs = [(a, "Prestige Group"), (b, "Prestige Estates"), (c, "DLF"), (d, "Orris Infrastructure"), (e, "Orris Infrastructure Ltd")]
    assert hidden_duplicates(pairs, {a, c}) == {b}                       # Prestige Estates; the two Orris rows are unseeded, so neither is hidden
    assert hidden_duplicates(pairs, set()) == set()                      # nothing seeded: nothing hidden
    assert hidden_duplicates(pairs, {b}) == {a}                          # the seeded one always stays; here the other is the unseeded one
    assert hidden_duplicates([(a, "Prestige Group"), (b, "Prestige Estates")], {a, b}) == set()   # two seeded ones are both kept
    assert duplicate_groups(["Prestige Group", "Prestige Estates", "DLF", "Orris Infrastructure", "Orris Infrastructure Ltd"]) == [
        ["Prestige Group", "Prestige Estates"], ["Orris Infrastructure", "Orris Infrastructure Ltd"]]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _benchmark_world(db):
    c = Client(id=uuid.uuid4(), name="Godrej Properties")
    db.add(c)
    db.commit()
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name="Godrej Properties", entity_type="brand")
    db.add(brand)
    names = ["Prestige Group", "Prestige Estates", "DLF", "Orris Infrastructure"]
    ents = {n: Entity(id=uuid.uuid4(), client_id=c.id, name=n, entity_type="competitor") for n in names}
    db.add_all(ents.values())
    db.commit()
    for i, (n, score) in enumerate([("Prestige Group", 83.0), ("Prestige Estates", 73.0), ("DLF", 70.0), ("Orris Infrastructure", 68.0)], 1):
        db.add(CompetitorBenchmark(id=uuid.uuid4(), client_id=c.id, competitor_entity_id=ents[n].id, reputation_score=score, executive_reputation_score=0.0,
                                   sentiment_score=0.0, risk_score=0.0, visibility_score=0.0, share_of_voice=2.0, rank=i, run_id="run-1",
                                   calculation_lineage={"client_comparable_score_exact": 75.0}, evidence_metadata={}, health_status="COMPLETE"))
    db.add_all([SeededEntity(id=uuid.uuid4(), client_id=c.id, entity_id=ents["Prestige Group"].id, kind="competitor", name="Prestige Group", rank=1, status="active"),
                SeededEntity(id=uuid.uuid4(), client_id=c.id, entity_id=ents["DLF"].id, kind="competitor", name="DLF", rank=2, status="active")])
    db.commit()
    return c, ents


def test_benchmark_hides_the_unseeded_duplicate_and_keeps_the_entity(db):
    c, ents = _benchmark_world(db)
    out = ci.get_client_benchmark(c.id, Response(), 25, 0, db)
    assert [r["competitor_name"] for r in out] == ["Prestige Group", "DLF", "Orris Infrastructure"]
    assert db.query(Entity).filter(Entity.id == ents["Prestige Estates"].id, Entity.entity_type == "competitor").count() == 1    # entity kept
    assert db.query(CompetitorBenchmark).filter(CompetitorBenchmark.competitor_entity_id == ents["Prestige Estates"].id).count() == 1
    assert out[0]["client_share_of_voice"] == 100.0 - 3 * 2.0                         # share of voice is computed from the rows shown


def test_benchmark_without_a_seeded_counterpart_is_untouched(db):
    c, ents = _benchmark_world(db)
    db.query(SeededEntity).filter(SeededEntity.name == "Prestige Group").delete()
    db.commit()
    out = ci.get_client_benchmark(c.id, Response(), 25, 0, db)
    assert "Prestige Estates" in [r["competitor_name"] for r in out] and "Prestige Group" in [r["competitor_name"] for r in out]
