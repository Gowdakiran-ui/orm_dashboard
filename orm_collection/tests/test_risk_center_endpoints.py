"""Risk Center page audit fixes (audit/risk-center-audit.md).

Runs entirely against an in-memory SQLite session, like
test_brand_equity_endpoints.py -- the functions take `db` as a parameter, so
nothing here touches a real database. DATABASE_URL is forced to an
unreachable dummy so an accidental SessionLocal() use could never reach
production.
"""
import os
import sys
import uuid
import datetime

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
from app.models.entity import Entity
from app.models.document import Document, DocumentMatch
from app.models.risk import RiskEvent
from app.models.source import Source, SourceCategory
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.services.intelligence.ai_summary_engine import AISummaryEngine
import app.api.endpoints.client_intelligence as ci
import app.api.endpoints.documents as docs_ep

UTC = datetime.timezone.utc


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
    session = sessionmaker(bind=engine)()
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


def _doc(db, brand, title="doc", published_at=None, collected_at=None, source_id=None):
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", normalized_content="x", title=title,
                 published_at=published_at, source_id=source_id)
    if collected_at is not None:
        d.collected_at = collected_at
    db.add(d)
    db.add(DocumentMatch(document_id=d.id, matched_entity_id=brand))
    db.commit()
    return d.id


def _event(db, cid, doc_id, entity_id, score, explainability=None, computed_at=None, level="X"):
    r = RiskEvent(client_id=cid, document_id=doc_id, entity_id=entity_id, risk_score=score, risk_level=level,
                  explainability=explainability, computed_at=computed_at)
    db.add(r)
    db.commit()
    return r


def _out(db, cid):
    docs = db.query(Document).all()
    return {d["title"]: d for d in docs_ep._build_document_responses(db, cid, docs)}


# ---------------------------------------------------------------------------
# Banding: unrounded, same rule as the engine (rounded `risk` can sit on the
# wrong side of a threshold by up to 0.5)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,rounded,level", [
    (25.0, 25, "LOW"),
    (25.3, 25, "MEDIUM"),      # rounds to 25 (LOW by the rounded number) but the engine bands it MEDIUM
    (32.23, 32, "MEDIUM"),
    (50.0, 50, "MEDIUM"),
    (50.2, 50, "HIGH"),
    (75.0, 75, "HIGH"),
    (75.4, 75, "CRITICAL"),
    (0.0, 0, "LOW"),
])
def test_document_level_uses_unrounded_score_like_the_engine(db, raw, rounded, level):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db, brand, "t")
    _event(db, cid, d, brand, raw)
    out = _out(db, cid)["t"]
    assert out["risk"] == rounded
    assert out["risk_level"] == level
    assert out["risk_exact"] == pytest.approx(raw)           # unrounded: the page decides how to show it
    # identical to what the engine itself would store
    from app.services.intelligence.risk_engine import RiskEngine
    assert out["risk_level"] == RiskEngine().get_risk_level(raw)


def test_unscored_document_has_no_level_and_no_exact_score(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    _doc(db, brand, "unscored")
    out = _out(db, cid)["unscored"]
    assert out["scored"] is False
    assert out["risk_level"] is None and out["risk_exact"] is None


def test_a_32_is_medium_in_the_table_the_summary_and_the_engine(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db, brand, "t")
    _event(db, cid, d, brand, 32.23)
    assert _out(db, cid)["t"]["risk_level"] == "MEDIUM"
    s = ci._document_risk_summary(db, cid)
    assert (s["total"], s["medium"], s["high"], s["critical"]) == (1, 1, 0, 0)


# ---------------------------------------------------------------------------
# Summary: unrounded banding, highest, as_of, counts independent of the table
# ---------------------------------------------------------------------------
def test_summary_counts_a_score_just_above_the_threshold_that_rounds_down(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    _event(db, cid, _doc(db, brand, "edge-low"), brand, 25.3)     # MEDIUM per engine
    _event(db, cid, _doc(db, brand, "edge-high"), brand, 50.2)    # HIGH per engine
    _event(db, cid, _doc(db, brand, "edge-crit"), brand, 75.4)    # CRITICAL per engine
    _event(db, cid, _doc(db, brand, "exact-25"), brand, 25.0)     # LOW
    s = ci._document_risk_summary(db, cid)
    assert (s["total"], s["critical"], s["high"], s["medium"]) == (3, 1, 1, 1)
    # and the summary agrees with every document's own band
    out = _out(db, cid)
    flagged_by_table = {t: o["risk_level"] for t, o in out.items() if o["risk_level"] not in (None, "LOW")}
    assert len(flagged_by_table) == s["total"]
    assert sorted(flagged_by_table.values()) == ["CRITICAL", "HIGH", "MEDIUM"]


def test_summary_highest_is_the_unrounded_maximum_and_null_when_none(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    assert ci._document_risk_summary(db, cid)["highest"] is None
    _event(db, cid, _doc(db, brand, "a"), brand, 33.4)
    _event(db, cid, _doc(db, brand, "b"), brand, 29.0)
    _event(db, cid, _doc(db, brand, "z"), brand, 10.0)            # LOW: not flagged, never the highest
    assert ci._document_risk_summary(db, cid)["highest"] == pytest.approx(33.4)
    _event(db, cid, _doc(db, brand, "c"), brand, 61.0)
    assert ci._document_risk_summary(db, cid)["highest"] == 61


def test_summary_highest_ignores_competitor_events(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    rival = _entity(db, cid, "Rival", "competitor")
    d = _doc(db, brand, "a")
    _event(db, cid, d, brand, 30.0)
    _event(db, cid, d, rival, 99.0)
    s = ci._document_risk_summary(db, cid)
    assert s["highest"] == pytest.approx(30.0) and s["total"] == 1


def test_summary_as_of_is_the_newest_score_time(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    assert ci._document_risk_summary(db, cid)["as_of"] is None
    older = datetime.datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    newer = datetime.datetime(2026, 10, 1, 19, 47, tzinfo=UTC)
    _event(db, cid, _doc(db, brand, "a"), brand, 30.0, computed_at=older)
    _event(db, cid, _doc(db, brand, "b"), brand, 5.0, computed_at=newer)   # newest, even though it is LOW
    got = ci._document_risk_summary(db, cid)["as_of"]
    assert got is not None and got.startswith("2026-10-01T19:47")


def test_summary_counts_are_not_capped_at_500_articles(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    base = datetime.datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(520):                     # the 20 risky ones are the OLDEST: outside a newest-500 window
        d = _doc(db, brand, f"d{i}", published_at=base + datetime.timedelta(hours=i))
        _event(db, cid, d, brand, 40.0 if i < 20 else 0.0)
    s = ci._document_risk_summary(db, cid)
    assert s["total"] == 20 and s["visible_documents"] == 520
    window = docs_ep.get_client_visible_documents(db, cid, limit=500)
    in_table = [o for o in docs_ep._build_document_responses(db, cid, window) if o["risk_level"] not in (None, "LOW")]
    assert len(in_table) == 0                # the table cannot show them; the tile still counts them


def test_summary_reports_unscored_articles_instead_of_counting_them_as_zero(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    _doc(db, brand, "unchecked")
    _event(db, cid, _doc(db, brand, "scored"), brand, 30.0)
    s = ci._document_risk_summary(db, cid)
    assert (s["visible_documents"], s["scored_documents"], s["unscored_documents"]) == (2, 1, 1)


def test_empty_client_summary_has_null_highest_average_and_as_of(db):
    cid = _client(db)
    r = ci._document_risk_summary(db, cid)
    assert r == {"visible_documents": 0, "scored_documents": 0, "unscored_documents": 0, "total": 0,
                 "critical": 0, "high": 0, "medium": 0, "average": None, "highest": None, "as_of": None, "top": []}


# ---------------------------------------------------------------------------
# Sentiment label read back from the stored weight; date basis
# ---------------------------------------------------------------------------
def _doc_sent(db, doc_id, label):
    db.add(DocumentSentiment(document_id=doc_id, sentiment_label=label, sentiment_score=0.0, confidence_score=1.0, weighted_sentiment_score=0.0))
    db.commit()


def _ent_sent(db, doc_id, entity_id, label):
    db.add(EntitySentiment(document_id=doc_id, entity_id=entity_id, sentiment_label=label, sentiment_score=0.0, confidence_score=1.0))
    db.commit()


def test_risk_sentiment_is_the_stored_document_label(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db, brand, "t")
    _event(db, cid, d, brand, 30.0)
    _doc_sent(db, d, "Negative")
    assert _out(db, cid)["t"]["risk_sentiment"] == "Negative"


def test_risk_sentiment_uses_the_scored_entitys_label_over_the_document_label(db):
    # same order the engine scores in: entity label when one exists, else document label
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db, brand, "t")
    _event(db, cid, d, brand, 30.0)
    _doc_sent(db, d, "Neutral")
    _ent_sent(db, d, brand, "Negative")
    assert _out(db, cid)["t"]["risk_sentiment"] == "Negative"


def test_risk_sentiment_ignores_another_entitys_label(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    person = _entity(db, cid, "P", "person")
    d = _doc(db, brand, "t")
    _event(db, cid, d, brand, 30.0)
    _doc_sent(db, d, "Neutral")
    _ent_sent(db, d, person, "Negative")          # a different entity: must not be used
    assert _out(db, cid)["t"]["risk_sentiment"] == "Neutral"


def test_risk_sentiment_is_none_when_no_label_is_stored_never_inferred_from_a_weight(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db, brand, "t")
    # the stored weight says 40 (Negative) but there is no stored label: nothing may be inferred
    _event(db, cid, d, brand, 30.0, explainability={"individual_weights": {"topic_weight": 0, "sentiment_weight": 40}})
    assert _out(db, cid)["t"]["risk_sentiment"] is None


def test_unscored_document_has_no_risk_sentiment(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db, brand, "t")
    _doc_sent(db, d, "Negative")
    assert _out(db, cid)["t"]["risk_sentiment"] is None


def test_date_basis_says_whether_timestamp_is_published_or_collected(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    _doc(db, brand, "pub", published_at=datetime.datetime(2026, 8, 13, tzinfo=UTC))
    _doc(db, brand, "col", published_at=None)
    out = _out(db, cid)
    assert out["pub"]["date_basis"] == "published"
    assert out["col"]["date_basis"] == "collected"


# ---------------------------------------------------------------------------
# AI Summary: what = the article (no scoring-time `when`)
# ---------------------------------------------------------------------------
def _source(db, name="Reuters"):
    cat = SourceCategory(id=uuid.uuid4(), name="cat", base_reliability_score=1.0)
    db.add(cat)
    db.commit()
    s = Source(id=uuid.uuid4(), category_id=cat.id, name=name, source_type="rss", schedule_cron="* * * * *")
    db.add(s)
    db.commit()
    return s.id


def _prepare(db, cid, re):
    return AISummaryEngine()._prepare_risk_event(db, re, "Acme", str(cid), "run")


def test_ai_summary_what_describes_the_article_not_the_scoring_reason(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db, brand, "Acme shares fall", published_at=datetime.datetime(2026, 1, 23, 8, 0, tzinfo=UTC), source_id=_source(db, "Reuters"))
    re = _event(db, cid, d, brand, 33.0, explainability={"decision_reason": "Risk level set to MEDIUM based on topic 'None' (weight 0)"}, level="MEDIUM")
    partial = _prepare(db, cid, re)["partial"]
    assert partial["what"] == '"Acme shares fall" (Reuters).'
    assert "weight" not in partial["what"] and "None" not in partial["what"]


def test_ai_summary_does_not_store_the_scoring_time_as_a_when(db):
    # the old `when` was the scoring run's timestamp (identical for everything scored in one run) and
    # nothing reads a risk event's `when`: the drawer shows the document's own date from the documents API
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    scored_at = datetime.datetime(2026, 10, 1, 14, 17, tzinfo=UTC)
    d = _doc(db, brand, "story", published_at=datetime.datetime(2023, 1, 25, 2, 54, tzinfo=UTC))
    re = _event(db, cid, d, brand, 33.0, computed_at=scored_at, level="MEDIUM")
    partial = _prepare(db, cid, re)["partial"]
    assert "when" not in partial
    assert "Oct 01, 2026" not in str(partial)


def test_ai_summary_without_a_document_says_so_instead_of_inventing(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    re = _event(db, cid, None, brand, 33.0, level="MEDIUM")
    partial = _prepare(db, cid, re)["partial"]
    assert partial["what"] == "Source article unavailable."


def test_ai_summary_cache_key_changes_when_the_description_changes(db):
    cid = _client(db)
    brand = _entity(db, cid, "Acme", "brand")
    d = _doc(db, brand, "story", published_at=datetime.datetime(2026, 8, 13, tzinfo=UTC))
    re = _event(db, cid, d, brand, 33.0, level="MEDIUM")
    first = _prepare(db, cid, re)["partial"]["_cache_key"]
    # an old stored summary (built from the old scoring-reason `what`) must not be treated as current
    re.explainability = {"ai_summary": {"_cache_key": "stale-key", "what": "Risk level set to MEDIUM..."}}
    db.commit()
    assert _prepare(db, cid, re) is not None and _prepare(db, cid, re)["partial"]["_cache_key"] == first != "stale-key"
