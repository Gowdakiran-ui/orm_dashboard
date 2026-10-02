"""No key containing "trend" may leave the system in an API payload or reach the LLM prompt input.

Trend detection was removed from scoring, but explainability stored by the old formula
(and merged forward on re-scores) still carries keys like `trend_contribution` and
`individual_weights.trend_weight`. The stored rows are intentionally NOT edited; the
keys are stripped where the data leaves the system (documents API, AI-summary inputs).

Runs against in-memory SQLite. DATABASE_URL is forced to an unreachable dummy and the
LLM HTTP call and the llm_call_log write are stubbed, so nothing here can reach a real
database or a real LLM.
"""
import copy
import json
import os
import sys
import uuid

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
from app.models.alert import Alert
import app.api.endpoints.documents as docs_ep
import app.services.intelligence.ai_summary_engine as ase
from app.services.intelligence.ai_summary_engine import AISummaryEngine
from app.utils.explainability import strip_trend_keys


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


def trend_key_paths(obj, path=""):
    """Every dict key (at any depth, inside lists too) that contains 'trend', case-insensitive."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}/{k}"
            if "trend" in str(k).lower():
                found.append(here)
            found.extend(trend_key_paths(v, here))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            found.extend(trend_key_paths(v, f"{path}[{i}]"))
    return found


# What old rows really look like (keys seen live) plus extra nesting / casing / list cases.
LEGACY_EXPLAINABILITY = {
    "engine_version": "5.2",
    "formula_version": "1.0",
    "trend_contribution": 12.5,
    "individual_weights": {"topic_weight": 0, "sentiment_weight": 40, "trend_weight": 10},
    "confidence": 0.5,
    "final_equation": "final_score = (topic + sentiment + trend) / 240",
    "deep": {"TrendScore": 1, "ok": {"is_trending_up": True, "kept": 3}, "rows": [{"trend_x": 1, "kept": 2}, [{"Trend": 9}]]},
    "ai_summary": {"how_to_solve": "Review the filing.", "source": "generated", "_cache_key": "k"},
}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _scored_document(db, explainability):
    c = Client(id=uuid.uuid4(), name="Acme")
    db.add(c)
    db.commit()
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name="Acme", entity_type="brand")
    db.add(brand)
    db.commit()
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", normalized_content="body", title="headline")
    db.add(d)
    db.add(DocumentMatch(document_id=d.id, matched_entity_id=brand.id))
    db.commit()
    db.add(RiskEvent(client_id=c.id, document_id=d.id, entity_id=brand.id, risk_score=33.0, risk_level="MEDIUM",
                     explainability=copy.deepcopy(explainability)))
    db.commit()
    return c.id, d.id


# ---------------------------------------------------------------------------
# the helper
# ---------------------------------------------------------------------------
def test_walker_itself_finds_trend_keys_at_every_depth():
    # guards the guard: the walker must be able to see all of the fixture's legacy keys
    assert len(trend_key_paths(LEGACY_EXPLAINABILITY)) == 6


def test_strip_removes_every_trend_key_at_every_depth_and_keeps_the_rest():
    out = strip_trend_keys(LEGACY_EXPLAINABILITY)
    assert trend_key_paths(out) == []
    assert out["individual_weights"] == {"topic_weight": 0, "sentiment_weight": 40}
    assert out["confidence"] == 0.5 and out["ai_summary"]["how_to_solve"] == "Review the filing."
    assert out["deep"]["ok"] == {"kept": 3}
    assert out["deep"]["rows"] == [{"kept": 2}, [{}]]


def test_strip_never_mutates_its_input_and_handles_non_dicts():
    before = copy.deepcopy(LEGACY_EXPLAINABILITY)
    strip_trend_keys(LEGACY_EXPLAINABILITY)
    assert LEGACY_EXPLAINABILITY == before
    assert strip_trend_keys(None) is None
    assert strip_trend_keys("trend") == "trend"      # values are not touched, only keys
    assert strip_trend_keys([1, {"a": 2}]) == [1, {"a": 2}]


# ---------------------------------------------------------------------------
# documents API
# ---------------------------------------------------------------------------
def test_documents_list_response_has_no_trend_key_anywhere(db):
    cid, _ = _scored_document(db, LEGACY_EXPLAINABILITY)
    resp = docs_ep._build_document_responses(db, cid, db.query(Document).all())
    assert resp and resp[0]["risk_explainability"] is not None
    assert trend_key_paths(resp) == []
    # the useful content is still there
    assert resp[0]["risk_explainability"]["confidence"] == 0.5
    assert resp[0]["risk_explainability"]["individual_weights"]["sentiment_weight"] == 40


def test_single_document_response_has_no_trend_key_anywhere(db):
    cid, did = _scored_document(db, LEGACY_EXPLAINABILITY)
    resp = docs_ep.read_document(did, cid, db)
    assert resp["risk_explainability"] is not None
    assert trend_key_paths(resp) == []


def test_stored_rows_are_not_edited(db):
    cid, did = _scored_document(db, LEGACY_EXPLAINABILITY)
    docs_ep._build_document_responses(db, cid, db.query(Document).all())
    docs_ep.read_document(did, cid, db)
    db.expire_all()
    stored = db.query(RiskEvent).filter(RiskEvent.document_id == did).one().explainability
    assert stored == LEGACY_EXPLAINABILITY
    assert len(trend_key_paths(stored)) == 6


def test_unscored_document_still_serializes(db):
    cid, _ = _scored_document(db, LEGACY_EXPLAINABILITY)
    db.query(RiskEvent).delete()
    db.commit()
    resp = docs_ep._build_document_responses(db, cid, db.query(Document).all())
    assert resp[0]["risk_explainability"] is None and trend_key_paths(resp) == []


# ---------------------------------------------------------------------------
# AI-summary prompt input
# ---------------------------------------------------------------------------
def _alert(db, cid, explainability, signals):
    ent = db.query(Entity).filter(Entity.client_id == cid).first()
    a = Alert(client_id=cid, entity_id=ent.id, alert_type="Multi-Signal Incident", severity="HIGH", title="t",
              evidence_score=71.0, confidence_score=80.0,
              explainability=copy.deepcopy(explainability), supporting_signals=copy.deepcopy(signals))
    db.add(a)
    db.commit()
    return a


ALERT_EXPLAINABILITY = {
    "supporting_evidence": {"max_risk_score": 40, "document_count": 3, "executive_involved": True, "trend_count": 9},
    "trend_contribution": 5,
    "decision_reason": "meets the threshold",
}
ALERT_SIGNALS = {"risks_count": 2, "trend_events": 7, "nested": {"trend_state": "UP"}}


def test_ai_summary_prompt_inputs_have_no_trend_key_for_an_alert(db):
    cid, _ = _scored_document(db, LEGACY_EXPLAINABILITY)
    alert = _alert(db, cid, ALERT_EXPLAINABILITY, ALERT_SIGNALS)
    out = AISummaryEngine()._prepare_alert(db, alert, "Acme", str(cid), "run")
    assert out["action"] == "generate"
    assert trend_key_paths(out["gen_kwargs"]) == []
    assert trend_key_paths(out["partial"]) == []
    # the sentence derived from the blobs still uses the real (non-trend) numbers
    assert out["gen_kwargs"]["what"] == "2 risk signals for Acme, backed by 3 documents, evidence score 71.0, confidence 80.0%, with executive involvement."
    assert "trend" not in out["gen_kwargs"]["what"].lower()


def test_ai_summary_prompt_inputs_have_no_trend_key_for_a_risk_event(db):
    cid, did = _scored_document(db, LEGACY_EXPLAINABILITY)
    re = db.query(RiskEvent).filter(RiskEvent.document_id == did).one()
    out = AISummaryEngine()._prepare_risk_event(db, re, "Acme", str(cid), "run")
    assert trend_key_paths(out["gen_kwargs"]) == []
    assert trend_key_paths(out["partial"]) == []
    # a risk event's prompt takes no explainability at all: only the article description
    assert out["gen_kwargs"]["what"] == '"headline".'


def test_the_request_actually_sent_to_the_llm_has_no_trend_key(db, monkeypatch):
    cid, _ = _scored_document(db, LEGACY_EXPLAINABILITY)
    alert = _alert(db, cid, ALERT_EXPLAINABILITY, ALERT_SIGNALS)
    out = AISummaryEngine()._prepare_alert(db, alert, "Acme", str(cid), "run")

    sent = {}

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"how_to_solve": "Review the filing."})}}], "usage": {}}

    import requests
    monkeypatch.setattr(requests, "post", lambda url, headers=None, json=None, timeout=None: sent.update(body=json, url=url) or _Resp())
    monkeypatch.setattr(ase, "log_llm_call", lambda **kw: None)       # never write llm_call_log
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")

    result = AISummaryEngine()._generate_how_to_solve(**out["gen_kwargs"])
    assert result == "Review the filing."
    assert sent["body"], "the LLM request was not captured"
    assert trend_key_paths(sent["body"]) == []                         # structured request body
    user_prompt = sent["body"]["messages"][1]["content"]
    assert "trend_count" not in user_prompt and "trend_events" not in user_prompt and "trend_state" not in user_prompt
    assert "Summary: 2 risk signals for Acme" in user_prompt           # and the real signals are still there


def test_alert_what_is_built_from_the_same_numbers_with_or_without_trend_keys(db):
    cid, _ = _scored_document(db, LEGACY_EXPLAINABILITY)
    clean = {"supporting_evidence": {"document_count": 3, "executive_involved": True}}
    a_trend = _alert(db, cid, ALERT_EXPLAINABILITY, ALERT_SIGNALS)
    a_clean = _alert(db, cid, clean, {"risks_count": 2})
    eng = AISummaryEngine()
    assert eng._build_alert_what(db, a_trend) == eng._build_alert_what(db, a_clean)
