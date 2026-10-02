"""Brand Equity page audit fixes (audit/brand-equity-audit.md).

Runs entirely against an in-memory SQLite session -- the engine/endpoint
functions take `db` as a parameter, so nothing here touches a real database.
DATABASE_URL is forced to an unreachable dummy so an accidental SessionLocal()
use could never reach production.
"""
import os
import sys
import uuid
import datetime
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import Response
from sqlalchemy import create_engine, null
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.document import Document
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.risk import RiskEvent
from app.models.alert import Alert
from app.models.reputation import ReputationScore
from app.models.executive_reputation import ExecutiveReputationScore
from app.models.competitor_benchmark import CompetitorBenchmark
from app.models.source import Source, SourceCategory
import app.api.endpoints.client_intelligence as ci
import app.api.endpoints.documents as docs_ep


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    # Bypass the Redis read-through cache so tests never depend on/ write Redis.
    monkeypatch.setattr(ci, "get_client_reputation_summary", ci.get_client_reputation_summary.__wrapped__)
    yield session
    session.close()


def _client(db, name="Acme"):
    c = Client(id=uuid.uuid4(), name=name)
    db.add(c)
    db.commit()
    return c.id


def _entity(db, client_id, name, etype):
    e = Entity(id=uuid.uuid4(), client_id=client_id, name=name, entity_type=etype)
    db.add(e)
    db.commit()
    return e.id


def _doc(db, title="doc"):
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", normalized_content="x", title=title)
    db.add(d)
    db.commit()
    return d.id


def _mention(db, doc_id, entity_id):
    db.add(EntityMention(document_id=doc_id, entity_id=entity_id, mention_count=1))
    db.commit()


def _sent(db, doc_id, entity_id, label):
    db.add(EntitySentiment(document_id=doc_id, entity_id=entity_id, sentiment_label=label, sentiment_score=0.0, confidence_score=1.0))
    db.commit()


def _summary(db, client_id):
    return ci.get_client_reputation_summary(client_id, Response(), db)


# ---------------------------------------------------------------------------
# Sentiment gate + explicit tie-break (audit #8)
# ---------------------------------------------------------------------------
def test_sentiment_excludes_person_sentiment_on_non_brand_documents(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    person = _entity(db, cid, "Some Person", "person")
    comp = _entity(db, cid, "Rival", "competitor")
    on_brand = _doc(db)
    off_brand = _doc(db)
    _mention(db, on_brand, brand)
    _mention(db, on_brand, person)
    _mention(db, off_brand, person)           # person only: no brand co-occurrence
    _sent(db, on_brand, brand, "Positive")
    _sent(db, on_brand, person, "Negative")
    _sent(db, off_brand, person, "Negative")  # must NOT count
    _sent(db, on_brand, comp, "Negative")     # competitor: must NOT count
    s = _summary(db, cid)["sentiment"]
    assert (s["positive"], s["neutral"], s["negative"]) == (1, 0, 1)


def test_sentiment_counts_change_when_input_changes(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    person = _entity(db, cid, "P", "person")
    d = _doc(db)
    _mention(db, d, person)                  # person only at first
    _sent(db, d, person, "Negative")
    before = _summary(db, cid)["sentiment"]
    assert before["negative"] == 0           # gated out
    _mention(db, d, brand)                   # now co-occurs with the brand
    after = _summary(db, cid)["sentiment"]
    assert after["negative"] == 1


def test_sentiment_without_any_brand_entity_is_not_gated(db):
    cid = _client(db)
    person = _entity(db, cid, "P", "person")
    d = _doc(db)
    _sent(db, d, person, "Neutral")
    assert _summary(db, cid)["sentiment"]["neutral"] == 1


def test_dominant_sentiment_tie_is_mixed_and_clear_winner_is_named(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    docs = [_doc(db) for _ in range(3)]
    for d in docs:
        _mention(db, d, brand)
    assert _summary(db, cid)["sentiment"]["dominant"] is None      # no readings
    _sent(db, docs[0], brand, "Positive")
    assert _summary(db, cid)["sentiment"]["dominant"] == "positive"
    _sent(db, docs[1], brand, "Negative")
    assert _summary(db, cid)["sentiment"]["dominant"] == "mixed"   # 1-1 tie, no silent preference
    _sent(db, docs[2], brand, "Negative")
    assert _summary(db, cid)["sentiment"]["dominant"] == "negative"


# ---------------------------------------------------------------------------
# Trend removal: no trend field in any payload this page / its consumers read
# ---------------------------------------------------------------------------
def _rep_row(db, cid, **kw):
    r = ReputationScore(client_id=cid, score=70.0, grade="B", confidence_score=0.9, data_coverage=None, **kw)
    db.add(r)
    db.commit()


def test_reputation_summary_has_no_trend_fields(db):
    cid = _client(db)
    _rep_row(db, cid)
    s = _summary(db, cid)
    assert "trend" not in s["reputation"]
    assert "trends" not in s
    assert "total" not in s["risk"]
    assert s["reputation"]["score"] == 70.0 and s["reputation"]["status"] == "ok"
    # no-data branch too
    cid2 = _client(db, "Empty")
    assert "trend" not in _summary(db, cid2)["reputation"]


def test_reputation_endpoint_has_no_trend_and_does_not_invent_coverage(db):
    cid = _client(db)
    assert ci.get_client_reputation(cid, db) == {"score": None, "grade": None, "confidence_score": None, "data_coverage": None}
    _rep_row(db, cid)
    out = ci.get_client_reputation(cid, db)
    assert "trend" not in out
    assert out["data_coverage"] is None      # stored NULL stays NULL (no 0.40 default)
    assert out["score"] == 70.0


def test_reputation_breakdown_and_executives_have_no_trend(db):
    cid = _client(db)
    assert "trend" not in ci.get_client_reputation_breakdown(cid, db)
    _rep_row(db, cid)
    assert "trend" not in ci.get_client_reputation_breakdown(cid, db)
    brand = _entity(db, cid, "Acme", "brand")
    exec_id = _entity(db, cid, "Jane Doe", "person")
    d = _doc(db)
    _mention(db, d, brand)
    _mention(db, d, exec_id)
    db.add(ExecutiveReputationScore(
        client_id=cid, entity_id=exec_id, executive_name="Jane Doe", score=60.0, grade="C",
        sentiment_component=1.0, risk_component=1.0, visibility_component=1.0,
        confidence_score=0.5, data_coverage=0.5,
    ))
    db.commit()
    rows = ci.get_client_executives(cid, db)
    assert len(rows) == 1 and rows[0]["name"] == "Jane Doe"
    assert "trend" not in rows[0]


def test_engines_no_longer_define_or_store_a_trend():
    from app.services.intelligence.reputation_engine import ReputationEngine
    from app.services.intelligence.executive_reputation_engine import ExecutiveReputationEngine
    assert not hasattr(ReputationEngine, "_determine_trend")
    assert not hasattr(ExecutiveReputationEngine, "_determine_trend")
    import inspect
    from app.services.intelligence import reputation_engine, executive_reputation_engine
    for mod in (reputation_engine, executive_reputation_engine):
        src = inspect.getsource(mod)
        assert "rep_trend" not in src and "IMPROVING" not in src and "DECLINING" not in src


def test_ai_serializer_output_has_no_trend():
    from app.services.ai import serializers
    rep = SimpleNamespace(score=1, grade="A", sentiment_component=1, risk_component=1, narrative_component=None,
                          source_component=1, visibility_component=1, confidence_score=1, health_status="COMPLETE",
                          calculation_lineage={})
    out = serializers.serialize_reputation(rep)
    assert not any("trend" in k for k in out)
    ex = serializers.serialize_executive_reputation(SimpleNamespace(id=uuid.uuid4(), executive_name="x", score=1, grade="A", health_status="C"))
    assert not any("trend" in k for k in ex)
    assert not hasattr(serializers, "serialize_trend_event")


def test_ai_prompts_do_not_ask_for_trend_analysis_or_forecast():
    import inspect
    from app.services.ai import prompt_builder
    from app.services.ai.advisor.advisor_schema import ReputationAdvisorResponse
    src = inspect.getsource(prompt_builder)
    assert "trend_analysis" not in src and "forecast" not in src.lower() and "fabricate trends" not in src
    assert "trend_analysis" not in ReputationAdvisorResponse.model_fields


# ---------------------------------------------------------------------------
# plan-advisory `flagged` (audit #9)
# ---------------------------------------------------------------------------
def test_plan_advisory_flagged_false_when_nothing_to_flag(db):
    cid = _client(db)
    out = ci.get_client_plan_advisory(cid, db)
    assert out["flagged"] is False and out["bullets"] == []


def test_plan_advisory_flagged_true_for_critical_risk(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db)
    db.add(RiskEvent(client_id=cid, document_id=d, entity_id=brand, risk_score=90.0, risk_level="CRITICAL",
                     risk_factors=[{"factor": "Legal", "weight": 40}]))
    db.commit()
    out = ci.get_client_plan_advisory(cid, db)
    assert out["flagged"] is True and "Critical" in out["lead"]


def test_plan_advisory_flagged_true_for_open_executive_alert(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    person = _entity(db, cid, "Jane", "person")
    d = _doc(db)
    _mention(db, d, brand)
    db.add(Alert(client_id=cid, document_id=d, entity_id=person, alert_type="Executive Risk", severity="CRITICAL",
                 title="Jane under fire", is_acknowledged=False, explainability={"contributing_documents": [str(d)]}))
    db.commit()
    out = ci.get_client_plan_advisory(cid, db)
    assert out["flagged"] is True and "Jane" in out["lead"]


# ---------------------------------------------------------------------------
# /benchmark: latest run only, current competitors only, engine rank/SOV
# ---------------------------------------------------------------------------
def _row(rank, sov, rep, name, health="COMPLETE", rid=None, eid=None):
    b = SimpleNamespace(id=uuid.uuid4(), competitor_entity_id=eid or uuid.uuid4(), rank=rank, share_of_voice=sov,
                        reputation_score=rep, sentiment_score=0.1, risk_score=5.0, visibility_score=10.0,
                        health_status=health, confidence_score=0.9, data_coverage=0.9)
    return (b, SimpleNamespace(name=name))


GODREJ_LIKE = lambda: [
    _row(1, 0.14, 88.24, "EMAAR"), _row(2, 1.58, 77.34, "DLF"), _row(3, 0.14, 76.47, "Banke"),
    _row(5, 1.58, 62.79, "Orris"), _row(6, 1.00, 51.73, "Lodha"),
    _row(0, 0.0, 0.0, "M3M", health="INSUFFICIENT_EVIDENCE"),
]


def test_benchmark_client_rank_counts_valid_competitors_with_a_higher_score():
    out = ci._build_benchmark_response(GODREJ_LIKE(), 74.16, 25, 0)
    assert {r["client_rank"] for r in out} == {4}      # EMAAR, DLF, Banke are higher; Orris, Lodha lower; M3M has no evidence
    assert out[0]["client_comparable_score"] == 74.16


def test_benchmark_client_rank_changes_with_the_client_score():
    rows = [_row(1, 1.0, 90.0, "A"), _row(2, 1.0, 80.0, "B")]
    assert ci._build_benchmark_response(rows, 95.0, 25, 0)[0]["client_rank"] == 1
    assert ci._build_benchmark_response(rows, 85.0, 25, 0)[0]["client_rank"] == 2
    assert ci._build_benchmark_response(rows, 70.0, 25, 0)[0]["client_rank"] == 3


def test_benchmark_rank_is_not_shifted_by_a_competitor_filtered_out_of_the_run():
    # Engine run stored: A=1, client=2, B=3, D=4. A is later re-typed as a person
    # and filtered out of what is served. The client is now behind nobody but B? No:
    # only B (80) and D (60) remain, client 85 -> rank 1. An inferred "missing rank
    # number" approach would have answered 1 (gap at 1) here but 2 or 3 in other
    # shapes; the score-based rule is independent of which ranks remain.
    served = [_row(3, 1.0, 80.0, "B"), _row(4, 1.0, 60.0, "D")]
    assert ci._build_benchmark_response(served, 85.0, 25, 0)[0]["client_rank"] == 1
    # Filtering out a competitor that was BELOW the client must not change the rank.
    full = [_row(1, 1.0, 90.0, "A"), _row(3, 1.0, 80.0, "B"), _row(4, 1.0, 60.0, "D")]
    without_d = [r for r in full if r[1].name != "D"]
    assert ci._build_benchmark_response(full, 85.0, 25, 0)[0]["client_rank"] == 2
    assert ci._build_benchmark_response(without_d, 85.0, 25, 0)[0]["client_rank"] == 2
    # Filtering out a competitor that was ABOVE the client moves it up exactly one place.
    without_a = [r for r in full if r[1].name != "A"]
    assert ci._build_benchmark_response(without_a, 85.0, 25, 0)[0]["client_rank"] == 1


def test_benchmark_rank_tie_rule_uses_entity_id_like_the_engine():
    low_id, high_id = uuid.UUID(int=1), uuid.UUID(int=2**100)
    client_id = uuid.UUID(int=2**50)
    rows = [_row(1, 1.0, 80.0, "Low", eid=low_id), _row(2, 1.0, 80.0, "High", eid=high_id)]
    # equal score: the competitor whose id sorts before the client's id is ahead, the other is not
    assert ci._build_benchmark_response(rows, 80.0, 25, 0, client_id)[0]["client_rank"] == 2
    # unknown client id: a tie is never counted as "ahead"
    assert ci._build_benchmark_response(rows, 80.0, 25, 0, None)[0]["client_rank"] == 1


def test_benchmark_no_evidence_and_unranked_rows_are_excluded_from_ranking():
    rows = [_row(1, 1.0, 50.0, "A"), _row(0, 0.0, 0.0, "NoEv", health="INSUFFICIENT_EVIDENCE"), _row(0, 0.0, 99.0, "Unranked")]
    assert ci._build_benchmark_response(rows, 40.0, 25, 0)[0]["client_rank"] == 2   # only A counts


def test_benchmark_client_unranked_when_engine_had_no_client_score():
    out = ci._build_benchmark_response([_row(1, 2.0, 80.0, "A")], None, 25, 0)
    assert out[0]["client_rank"] is None and out[0]["client_comparable_score"] is None


def test_benchmark_sov_uses_all_rows_not_the_page_and_zero_row_placeholder_is_null():
    rows = GODREJ_LIKE()
    full = ci._build_benchmark_response(rows, 74.16, 25, 0)
    paged = ci._build_benchmark_response(rows, 74.16, 2, 0)
    assert len(paged) == 2 and len(full) == 6
    assert paged[0]["client_share_of_voice"] == pytest.approx(95.56, abs=0.01)
    assert full[0]["client_share_of_voice"] == paged[0]["client_share_of_voice"]    # independent of any display cap
    m3m = [r for r in full if r["competitor_name"] == "M3M"][0]
    assert m3m["reputation"] is None and m3m["rank"] == 0          # 0.0 placeholder never exposed as a score


def test_benchmark_order_is_deterministic_ranked_first_then_by_name():
    out = ci._build_benchmark_response(GODREJ_LIKE(), 74.16, 25, 0)
    assert [r["competitor_name"] for r in out] == ["EMAAR", "DLF", "Banke", "Orris", "Lodha", "M3M"]


def test_benchmark_no_rows_means_no_rank_and_no_share_of_voice():
    assert ci._build_benchmark_response([], 74.0, 25, 0) == []


def _bench(db, cid, comp_id, run, created, rank, sov, rep, lineage=None, health="COMPLETE"):
    db.add(CompetitorBenchmark(client_id=cid, competitor_entity_id=comp_id, reputation_score=rep,
                               executive_reputation_score=0.0, sentiment_score=0.0, risk_score=0.0,
                               visibility_score=1.0, share_of_voice=sov, rank=rank, run_id=run,
                               calculation_lineage=lineage, health_status=health, confidence_score=0.9,
                               data_coverage=0.9, created_at=created))
    db.commit()


def test_benchmark_endpoint_serves_only_latest_run_and_current_competitors(db):
    cid = _client(db)
    now = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.timezone.utc)
    old = now - datetime.timedelta(days=25)
    live = _entity(db, cid, "DLF", "competitor")
    retyped = _entity(db, cid, "Nadir Godrej", "person")          # was a competitor, now a person
    gone = _entity(db, cid, "M3M", "competitor")                  # no row in the latest run
    _bench(db, cid, retyped, "run-old", old, 1, 1.14, 71.8)
    _bench(db, cid, gone, "run-old", old, 2, 0.5, 60.0)
    _bench(db, cid, live, "run-new", now, 1, 1.58, 77.3, lineage={"client_comparable_score": 70.0})
    out = ci.get_client_benchmark(cid, Response(), 25, 0, db)
    assert [r["competitor_name"] for r in out] == ["DLF"]
    assert out[0]["client_share_of_voice"] == pytest.approx(98.42)
    assert out[0]["client_rank"] == 2 and out[0]["client_comparable_score"] == 70.0


def test_benchmark_endpoint_no_competitors_sentinel(db):
    cid = _client(db)
    assert ci.get_client_benchmark(cid, Response(), 25, 0, db) == [{"message": "No competitor intelligence available."}]


# ---------------------------------------------------------------------------
# documents: unscored documents are distinguishable from scored-zero (B9)
# ---------------------------------------------------------------------------
def test_unscored_documents_are_flagged_not_treated_as_scored_zero(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    scored, unscored, zero = _doc(db, "scored"), _doc(db, "unscored"), _doc(db, "zero")
    for d in (scored, unscored, zero):
        _mention(db, d, brand)
    db.add(RiskEvent(client_id=cid, document_id=scored, entity_id=brand, risk_score=40.0, risk_level="MEDIUM"))
    db.add(RiskEvent(client_id=cid, document_id=zero, entity_id=brand, risk_score=0.0, risk_level="LOW"))
    db.commit()
    docs = db.query(Document).all()
    out = {d["title"]: d for d in docs_ep._build_document_responses(db, cid, docs)}
    assert out["scored"]["scored"] is True and out["scored"]["risk"] == 40
    assert out["zero"]["scored"] is True and out["zero"]["risk"] == 0
    assert out["unscored"]["scored"] is False


# ---------------------------------------------------------------------------
# `base_score or 1.00` masking (B9): NULL skipped, 0.0 preserved
# ---------------------------------------------------------------------------
def _source_fixture(db, cid, base_score):
    brand = _entity(db, cid, "Acme", "brand")
    # null() forces a real SQL NULL (a plain None would fall back to the column default 1.00)
    cat = SourceCategory(id=uuid.uuid4(), name="cat", base_reliability_score=null() if base_score is None else base_score)
    db.add(cat)
    db.commit()
    src = Source(id=uuid.uuid4(), category_id=cat.id, name="s", source_type="rss", schedule_cron="* * * * *")
    db.add(src)
    db.commit()
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", normalized_content="x", source_id=src.id)
    db.add(d)
    db.commit()
    db.add(EntityMention(document_id=d.id, entity_id=brand, mention_count=1,
                         created_at=datetime.datetime.now(datetime.timezone.utc)))
    db.commit()
    return brand


@pytest.mark.parametrize("base,expected", [(None, None), (0.0, 0.0), (0.5, 50.0), (1.0, 100.0)])
def test_benchmark_source_component_null_skipped_zero_preserved(db, base, expected):
    from app.services.intelligence.benchmark_engine import BenchmarkEngine
    cid = _client(db)
    brand = _source_fixture(db, cid, base)
    inputs = BenchmarkEngine()._preload_score_inputs(
        db, cid, [brand], datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30),
        SimpleNamespace(warning=lambda *a, **k: None),
    )
    comp = inputs["components_for"](brand)["source"]
    assert comp == expected if expected is None else comp == pytest.approx(expected)


@pytest.mark.parametrize("base,expected", [(None, None), (0.0, 0.0), (1.0, 100.0)])
def test_reputation_engine_source_component_null_skipped_zero_preserved(db, base, expected):
    """The engine's Postgres upsert can't run on SQLite, so capture the statement
    it would execute and read the component values from it."""
    from app.services.intelligence.reputation_engine import ReputationEngine
    cid = _client(db)
    _source_fixture(db, cid, base)
    captured = []
    real_execute = db.execute

    def spy(stmt, *a, **k):
        # Only the engine's INSERT ... ON CONFLICT is captured (it is Postgres-only);
        # every other statement runs normally against SQLite.
        if getattr(stmt, "is_insert", False):
            captured.append(stmt)
            return None
        return real_execute(stmt, *a, **k)

    db.execute = spy
    try:
        ReputationEngine().calculate_reputation_score(db, cid)
    finally:
        db.execute = real_execute
    params = captured[0].compile().params
    # The engine passes no trend value at all (neither computed nor placeholder);
    # the model default supplies the constant for the still-NOT-NULL column.
    passed = {getattr(k, "key", k) for k in captured[0]._values}
    assert "reputation_trend" not in passed and "trend_component" not in passed
    got = params["source_component"]
    assert got == expected if expected is None else got == pytest.approx(expected)


def test_model_default_fills_the_not_null_trend_column_with_a_constant_placeholder(db):
    """An insert shaped like the engine's (no trend value) must succeed and store
    the constant, never a computed direction."""
    from sqlalchemy import insert
    cid = _client(db)
    db.execute(insert(ReputationScore).values(id=uuid.uuid4(), client_id=cid, score=70.0, confidence_score=0.5))
    db.commit()
    row = db.query(ReputationScore).filter(ReputationScore.client_id == cid).one()
    assert row.reputation_trend == "NOT_COMPUTED"
    assert row.data_coverage is None            # no invented 0.40


# ---------------------------------------------------------------------------
# Phase 3: server-side document risk counts (no 500-document window)
# ---------------------------------------------------------------------------
from app.models.document import DocumentMatch


def _visible_doc(db, brand, title, scores=(), competitor=None):
    """A document matched to the brand (so it is visible) with one RiskEvent per score."""
    d = _doc(db, title)
    db.add(DocumentMatch(document_id=d, matched_entity_id=brand))
    db.commit()
    for sc in scores:
        db.add(RiskEvent(client_id=db.info["cid"], document_id=d, entity_id=brand, risk_score=sc, risk_level="X"))
    db.commit()
    return d


def test_document_risk_counts_per_document_with_unscored_reported(db):
    cid = _client(db)
    db.info["cid"] = cid
    brand = _entity(db, cid, "Acme", "brand")
    rival = _entity(db, cid, "Rival", "competitor")
    _visible_doc(db, brand, "zero", scores=[0.0])
    _visible_doc(db, brand, "med-low", scores=[30.0, 10.0])         # one doc, max 30 -> medium, counted once
    _visible_doc(db, brand, "high", scores=[60.4])                    # rounds to 60 -> high
    _visible_doc(db, brand, "crit", scores=[90.0])
    _visible_doc(db, brand, "unchecked")                              # visible but no RiskEvent
    comp_doc = _visible_doc(db, brand, "competitor-only")             # only a competitor's event -> not this client's risk
    db.add(RiskEvent(client_id=cid, document_id=comp_doc, entity_id=rival, risk_score=99.0, risk_level="X"))
    db.commit()
    r = ci._document_risk_summary(db, cid)
    assert (r["visible_documents"], r["scored_documents"], r["unscored_documents"]) == (6, 4, 2)
    assert (r["total"], r["critical"], r["high"], r["medium"]) == (3, 1, 1, 1)
    assert r["average"] == pytest.approx((30 + 60 + 90) / 3)
    assert [t["title"] for t in r["top"]] == ["crit", "high"]
    assert [t["risk"] for t in r["top"]] == [90, 60]


def test_document_risk_summary_is_not_limited_to_500_documents(db):
    cid = _client(db)
    db.info["cid"] = cid
    brand = _entity(db, cid, "Acme", "brand")
    # 520 visible documents; the 20 risky ones are the OLDEST, i.e. outside a latest-500 window.
    for i in range(520):
        d = Document(id=uuid.uuid4(), url=f"http://t.test/{i}", normalized_content="x", title=f"d{i}",
                     published_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=i))
        db.add(d)
        db.add(DocumentMatch(document_id=d.id, matched_entity_id=brand))
        db.add(RiskEvent(client_id=cid, document_id=d.id, entity_id=brand, risk_score=40.0 if i < 20 else 0.0, risk_level="X"))
    db.commit()
    r = ci._document_risk_summary(db, cid)
    assert r["visible_documents"] == 520
    assert r["total"] == 20 and r["medium"] == 20          # a 500-row window would have shown 0


def test_document_risk_summary_empty_client_has_no_average(db):
    cid = _client(db)
    r = ci._document_risk_summary(db, cid)
    assert r == {"visible_documents": 0, "scored_documents": 0, "unscored_documents": 0, "total": 0,
                 "critical": 0, "high": 0, "medium": 0, "average": None, "top": []}


def test_reputation_summary_exposes_document_risk_block(db):
    cid = _client(db)
    s = _summary(db, cid)
    assert "document_risk" in s and s["document_risk"]["total"] == 0


def test_benchmark_endpoint_prefers_the_exact_client_score_and_uses_client_entity_id(db):
    cid = _client(db)
    now = datetime.datetime(2026, 10, 1, 12, 0, tzinfo=datetime.timezone.utc)
    a = _entity(db, cid, "A", "competitor")
    b = _entity(db, cid, "B", "competitor")
    meta = {"client_entity_id": str(uuid.uuid4())}
    # A is 74.162, B is 74.158; client exact score 74.160 (rounded lineage value 74.16).
    for ent, rank, rep in ((a, 1, 74.162), (b, 3, 74.158)):
        db.add(CompetitorBenchmark(client_id=cid, competitor_entity_id=ent, reputation_score=rep, executive_reputation_score=0.0,
                                   sentiment_score=0.0, risk_score=0.0, visibility_score=1.0, share_of_voice=1.0, rank=rank,
                                   run_id="r1", health_status="COMPLETE", confidence_score=0.9, data_coverage=0.9,
                                   calculation_lineage={"client_comparable_score": 74.16, "client_comparable_score_exact": 74.160},
                                   evidence_metadata=meta, created_at=now))
    db.commit()
    out = ci.get_client_benchmark(cid, Response(), 25, 0, db)
    assert out[0]["client_comparable_score"] == 74.160
    assert out[0]["client_rank"] == 2        # only A (74.162) is above 74.160; the rounded 74.16 would still give 2 here but ties would not


# ---------------------------------------------------------------------------
# Backend static guard: no trend identifier, key or string in the payload/engine/AI code
# ---------------------------------------------------------------------------
def _non_docstring_strings_and_names(path):
    import ast
    tree = ast.parse(open(path, encoding="utf-8").read())
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
                doc_nodes.add(id(first.value))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_nodes:
            found.append(node.value)
        elif isinstance(node, ast.Name):
            found.append(node.id)
        elif isinstance(node, ast.Attribute):
            found.append(node.attr)
        elif isinstance(node, ast.arg):
            found.append(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append(node.name)
    return found


@pytest.mark.parametrize("rel", [
    "app/api/endpoints/client_intelligence.py",
    "app/services/intelligence/reputation_engine.py",
    "app/services/intelligence/executive_reputation_engine.py",
    "app/services/intelligence/ai_summary_engine.py",
    "app/services/ai/serializers.py",
    "app/services/ai/schemas.py",
    "app/services/ai/validators.py",
])
def test_no_trend_identifier_key_or_string_in_code(rel):
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    hits = [t for t in _non_docstring_strings_and_names(os.path.join(root, rel)) if "trend" in t.lower()]
    assert hits == [], hits
