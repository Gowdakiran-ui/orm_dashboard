"""Executive auto-promotion gate (audit/risk-center-audit.md, 2026-10-02: 'Rachel Carson' was auto-promoted to a Godrej person entity).

In-memory SQLite; DATABASE_URL forced to an unreachable dummy. Wikidata, the matching engine refresh, the document re-match and the
executive reputation recalculation are stubbed, so nothing here touches a network, Redis or a real database."""
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
from app.models.entity import Entity, EntityMention, EntityKeyword
from app.models.document import Document
from app.models.executive_candidate import ExecutiveCandidate
import app.services.intelligence.entity_discovery as ed
from app.services.intelligence.entity_discovery import EntityDiscoveryEngine, EntityDiscoveryConfig


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


# The shipped default, read before any test can change it.
SHIPPED_DEFAULT_ENABLED = EntityDiscoveryConfig.EXECUTIVE_AUTO_PROMOTION_ENABLED


class _Stub:
    def refresh_processor(self, db):
        return None


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    eng = EntityDiscoveryEngine()
    # The gate rules are tested with the switch on; it ships OFF (see the default test below).
    monkeypatch.setattr(EntityDiscoveryConfig, "EXECUTIVE_AUTO_PROMOTION_ENABLED", True)
    # isolate the gate under test from external/slow collaborators
    monkeypatch.setattr(ed, "engine_instance", _Stub())
    monkeypatch.setattr(eng, "_is_valid_person_name_layered", lambda *a, **k: (True, "", ""))
    monkeypatch.setattr(eng, "_find_near_duplicate_person_entity", lambda *a, **k: None)
    monkeypatch.setattr(eng, "_rematch_recent_documents_for_new_entity", lambda *a, **k: None)
    monkeypatch.setattr(eng, "_client_self_reference_terms", lambda *a, **k: set())
    import app.services.intelligence.executive_reputation_engine as xre
    monkeypatch.setattr(xre.ExecutiveReputationEngine, "calculate_executive_reputation", lambda self, db, cid: None)
    # Production stores source_documents as JSON strings and Postgres coerces them to UUID in queries; SQLite's UUID type does
    # not. Keep the REAL helpers (the title-context scan is part of what is under test) and only adapt the id type here.
    real_ctx, real_text = eng._has_executive_context, eng._first_source_document_text

    def _uuids(ids):
        out = []
        for x in ids or []:
            try:
                out.append(uuid.UUID(str(x)))
            except ValueError:
                pass
        return out
    monkeypatch.setattr(eng, "_has_executive_context", lambda db, name, doc_ids, title_pattern=None: real_ctx(db, name, _uuids(doc_ids), title_pattern=title_pattern))
    monkeypatch.setattr(eng, "_first_source_document_text", lambda db, doc_ids: real_text(db, _uuids(doc_ids)))
    eng.kb = ("confirmed", True)
    monkeypatch.setattr(eng, "_check_person_via_kb", lambda name: (
        (eng.kb[1], eng.kb[0], "stub") if eng.kb[0] != "rejected" else (False, "rejected", "stub")))
    yield db, eng
    db.close()


def _client_with_brand(db, with_brand=True):
    c = Client(id=uuid.uuid4(), name=f"Acme-{uuid.uuid4().hex[:6]}")
    db.add(c)
    db.commit()
    brand = None
    if with_brand:
        brand = Entity(id=uuid.uuid4(), client_id=c.id, name="Acme", entity_type="brand")
        db.add(brand)
        db.commit()
    return c.id, brand


def _doc(db, text, brand=None):
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", normalized_content=text, title=text[:30])
    db.add(d)
    db.commit()
    if brand is not None:
        db.add(EntityMention(document_id=d.id, entity_id=brand.id, mention_count=1))
        db.commit()
    return str(d.id)


def _cand(db, cid, name, docs, mentions=2, conf=0.70):
    cand = ExecutiveCandidate(client_id=cid, name=name, mention_count=mentions, confidence=conf, source_documents=docs)
    db.add(cand)
    db.commit()
    return cand


def _promoted(db, cid, name):
    return db.query(Entity).filter(Entity.client_id == cid, Entity.name == name, Entity.entity_type == "person").count()


def test_rachel_carson_regression_unrelated_documents_never_promote_even_when_wikidata_confirms(env):
    db, eng = env
    cid, brand = _client_with_brand(db)
    docs = [_doc(db, "An exhibit on Rachel Carson's environmental vision"), _doc(db, "Writer reflects on Rachel Carson's legacy at lecture")]
    _cand(db, cid, "Rachel Carson", docs)
    out = eng.promote_executive_candidates(db, cid)
    assert out["promoted_count"] == 0 and _promoted(db, cid, "Rachel Carson") == 0
    assert db.query(EntityKeyword).count() == 0


def test_related_documents_without_an_executive_title_do_not_promote_a_wikidata_confirmed_human(env):
    db, eng = env
    cid, brand = _client_with_brand(db)
    docs = [_doc(db, "Acme shares fall; analyst Anil Singhvi says buy", brand), _doc(db, "Acme results: Anil Singhvi on the market", brand)]
    _cand(db, cid, "Anil Singhvi", docs)
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 0     # before the fix: promoted (KB confirmed bypassed the title check)
    assert _promoted(db, cid, "Anil Singhvi") == 0


def test_related_documents_with_an_executive_title_do_promote(env):
    db, eng = env
    cid, brand = _client_with_brand(db)
    docs = [_doc(db, "Acme chairman Jane Roe said profits rose", brand), _doc(db, "Acme CEO Jane Roe on the new launch", brand)]
    cand = _cand(db, cid, "Jane Roe", docs)
    out = eng.promote_executive_candidates(db, cid)
    assert out["promoted_count"] == 1 and _promoted(db, cid, "Jane Roe") == 1
    db.refresh(cand)
    assert cand.promoted_to_executive_id is not None
    assert db.query(EntityKeyword).filter(EntityKeyword.keyword_text == "Jane Roe").count() == 1


def test_wikidata_unresolved_still_promotes_a_real_executive_with_title_and_client_documents(env):
    db, eng = env
    cid, brand = _client_with_brand(db)
    eng.kb = ("unresolved", True)
    docs = [_doc(db, "Acme managing director Ravi Kumar announced", brand), _doc(db, "Ravi Kumar, Chief Financial Officer of Acme, said", brand)]
    _cand(db, cid, "Ravi Kumar", docs)
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 1


def test_wikidata_rejection_still_blocks_everything_else_passing(env):
    db, eng = env
    cid, brand = _client_with_brand(db)
    eng.kb = ("rejected", False)
    docs = [_doc(db, "Acme chairman Godrej Plots said", brand), _doc(db, "Acme CEO Godrej Plots said", brand)]
    _cand(db, cid, "Godrej Plots", docs)
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 0


def test_only_one_related_document_is_not_enough(env):
    db, eng = env
    cid, brand = _client_with_brand(db)
    docs = [_doc(db, "Acme chairman Jane Roe said profits rose", brand), _doc(db, "Chairman Jane Roe spoke at an unrelated conference")]
    _cand(db, cid, "Jane Roe", docs)
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 0


def test_numeric_thresholds_are_still_enforced(env):
    db, eng = env
    cid, brand = _client_with_brand(db)
    docs = [_doc(db, "Acme chairman Jane Roe said", brand)]
    _cand(db, cid, "Jane Roe", docs, mentions=1, conf=0.60)
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 0


def test_auto_promotion_ships_off_and_a_pass_creates_no_person_entity_or_keyword(env, monkeypatch):
    db, eng = env
    assert SHIPPED_DEFAULT_ENABLED is False                 # no env var or config can flip it: it is a class constant
    cid, brand = _client_with_brand(db)
    docs = [_doc(db, "Acme chairman Jane Roe said profits rose", brand), _doc(db, "Acme CEO Jane Roe on the launch", brand)]
    cand = _cand(db, cid, "Jane Roe", docs)                 # would pass every gate rule if the switch were on
    monkeypatch.setattr(EntityDiscoveryConfig, "EXECUTIVE_AUTO_PROMOTION_ENABLED", SHIPPED_DEFAULT_ENABLED)
    entities_before = db.query(Entity).count()
    out = eng.promote_executive_candidates(db, cid)
    assert out == {"promoted_count": 0, "promoted_executives": [], "auto_promotion_disabled": True}
    db.refresh(cand)
    assert cand.promoted_to_executive_id is None and _promoted(db, cid, "Jane Roe") == 0
    assert db.query(Entity).count() == entities_before and db.query(EntityKeyword).count() == 0
    monkeypatch.setattr(EntityDiscoveryConfig, "EXECUTIVE_AUTO_PROMOTION_ENABLED", True)
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 1       # same data promotes once re-enabled


def test_visitor_title_case_is_a_known_gap_the_switch_exists_for(env):
    """Documents the 2026-10-02 Adani case: a head of state named beside the chairman, in client-related documents, with 'President' beside his
    name, passes the gate rules. This is why the switch ships off; the test pins the behaviour so a future gate change is a visible decision."""
    db, eng = env
    cid, brand = _client_with_brand(db)
    docs = [_doc(db, "Acme Chairman Jane Roe meets South African President Cyril Ramaphosa in Delhi", brand),
            _doc(db, "BRICS: Acme Chairman Jane Roe welcomes South Africa President Cyril Ramaphosa", brand)]
    _cand(db, cid, "Cyril Ramaphosa", docs, conf=0.85)
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 1


def test_client_without_a_brand_entity_skips_only_the_relatedness_gate_title_still_required(env):
    db, eng = env
    cid, _ = _client_with_brand(db, with_brand=False)
    no_title = [_doc(db, "Some text about Jane Roe"), _doc(db, "More text about Jane Roe")]
    _cand(db, cid, "Jane Roe", no_title)
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 0
    cid2, _ = _client_with_brand(db, with_brand=False)
    with_title = [_doc(db, "Chairman Jane Roe said"), _doc(db, "CEO Jane Roe said")]
    _cand(db, cid2, "Jane Roe", with_title)
    assert eng.promote_executive_candidates(db, cid2)["promoted_count"] == 1


def test_malformed_source_document_ids_do_not_crash_the_batch(env):
    db, eng = env
    cid, brand = _client_with_brand(db)
    _cand(db, cid, "Jane Roe", ["not-a-uuid", "also-bad"])
    assert eng.promote_executive_candidates(db, cid)["promoted_count"] == 0
