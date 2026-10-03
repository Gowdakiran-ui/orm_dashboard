"""Executives page fixes (audit/executives-forensics-report.md F01-F17).

In-memory SQLite, DATABASE_URL forced to an unreachable dummy; the route functions are called directly. Nothing here touches a
network, Redis or a real database."""
import datetime as dt
import inspect
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

import app.api.endpoints.client_intelligence as ci  # imports the models so create_all sees every table
from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityMention, EntityKeyword
from app.models.user import User, UserClientAccess, ROLE_CLIENT_USER, ROLE_SUPER_ADMIN
from app.models.document import Document
from app.models.sentiment import DocumentSentiment
from app.models.rss_feed import RSSFeed
from app.models.collection_job import CollectionJob
from app.models.executive_candidate import ExecutiveCandidate
from app.models.executive_reputation import ExecutiveReputationScore
import app.services.intelligence.entity_discovery as ed


@compiles(PG_UUID, "sqlite")
def _compile_uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _compile_jsonb(element, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    eng = ed.entity_discovery_engine
    monkeypatch.setattr(eng, "_is_valid_person_name_layered", lambda *a, **k: (True, "", ""))
    real_ctx = eng._has_executive_context

    def _uuids(ids):
        out = []
        for x in ids or []:
            try:
                out.append(uuid.UUID(str(x)))
            except ValueError:
                pass
        return out
    monkeypatch.setattr(eng, "_has_executive_context", lambda db_, name, doc_ids, title_pattern=None: real_ctx(db_, name, _uuids(doc_ids), title_pattern=title_pattern))
    yield db, eng
    db.close()


def _client(db, brand_name="Godrej Properties"):
    c = Client(id=uuid.uuid4(), name=brand_name)
    db.add(c)
    db.commit()
    brand = Entity(id=uuid.uuid4(), client_id=c.id, name=brand_name, entity_type="brand")
    db.add(brand)
    db.commit()
    return c, brand


def _person(db, cid, name):
    e = Entity(id=uuid.uuid4(), client_id=cid, name=name, entity_type="person")
    db.add(e)
    db.commit()
    return e


def _doc(db, text, brand=None, person=None, title=None, sentiment=None):
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", normalized_content=text, title=title or text[:40])
    db.add(d)
    db.commit()
    if brand is not None:
        db.add(EntityMention(document_id=d.id, entity_id=brand.id, mention_count=1))
    if person is not None:
        db.add(EntityMention(document_id=d.id, entity_id=person.id, mention_count=1))
    if sentiment is not None:
        db.add(DocumentSentiment(document_id=d.id, sentiment_score=sentiment, sentiment_label="x", confidence_score=0.9, weighted_sentiment_score=sentiment))
    db.commit()
    return d


def _score(db, person, docs, score=57.98, grade="D", health="PARTIAL", created=None):
    lineage = {
        "component_scores": {"sentiment": 54.5, "risk": 100.0, "visibility": 2.2},
        "component_weights": {"sentiment": 0.35, "risk": 0.30, "visibility": 0.10},
        "raw_values": {"document_count": len(docs)},
    }
    row = ExecutiveReputationScore(
        client_id=person.client_id, entity_id=person.id, executive_name=person.name, score=score, grade=grade,
        confidence_score=0.8, data_coverage=0.8, health_status=health, calculation_lineage=lineage,
        evidence_metadata={"supporting_documents": [str(d.id) for d in docs]},
    )
    if created is not None:
        row.created_at = created
    db.add(row)
    db.commit()
    return row


def _writes(db):
    return tuple(db.query(m).count() for m in (Entity, EntityKeyword, RSSFeed, CollectionJob, ExecutiveCandidate))


# ---------------------------------------------------------------- X1: search is read-only
def test_search_of_an_unseen_string_creates_nothing(env):
    db, _ = env
    c, brand = _client(db)
    _person(db, c.id, "Pirojsha Godrej")
    before = _writes(db)
    out = ci.search_client_executive(c.id, "Suraj Kumar", db)
    assert out == {"status": "not_found"}
    assert _writes(db) == before


def test_glued_or_malformed_names_are_rejected_and_create_nothing(env):
    db, _ = env
    c, _b = _client(db)
    before = _writes(db)
    for bad in ["Nadir GodrejGautam Adani", "John Smith 3rd", "x" * 90, "Name<script>"]:
        out = ci.search_client_executive(c.id, bad, db)
        assert out["status"] == "invalid_name" and out["reason"]
    assert _writes(db) == before
    # real names that contain internal capitals are fine
    assert ci.search_client_executive(c.id, "Thalles DeSouza", db)["status"] == "not_found"


def test_search_never_runs_the_engine_or_polls_for_an_unscored_person(env, monkeypatch):
    db, _ = env
    c, brand = _client(db)
    p = _person(db, c.id, "Pranav Adani")
    _doc(db, "Godrej Properties and Pranav Adani", brand, p)
    import app.services.intelligence.executive_reputation_engine as xre
    monkeypatch.setattr(xre.ExecutiveReputationEngine, "process_client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("engine must not run")))
    before = _writes(db)
    out = ci.search_client_executive(c.id, "pranav adani", db)   # case-insensitive exact
    assert out["status"] == "tracked"
    e = out["executive"]
    assert e["score"] is None and e["grade"] is None and e["health_status"] == "NO_SCORE_YET"
    assert e["events"] == [] and e["document_count"] is None
    assert _writes(db) == before


def test_tracked_scored_executive_event_count_equals_document_count(env):
    db, _ = env
    c, brand = _client(db)
    p = _person(db, c.id, "Pirojsha Godrej")
    docs = [_doc(db, f"Godrej Properties chairman Pirojsha Godrej said {i}", brand, p, sentiment=s)
            for i, s in enumerate([0.9, 0.0, -0.9, 0.1])]
    other = _doc(db, "Old unrelated Godrej article not in the score", brand, p)   # not in supporting_documents
    _score(db, p, docs)
    out = ci.search_client_executive(c.id, "Pirojsha Godrej", db)
    e = out["executive"]
    assert out["status"] == "tracked" and e["document_count"] == 4
    assert len(e["events"]) == e["document_count"]
    assert other.id.hex not in {x["id"].replace("-", "") for x in e["events"]}
    assert e["sentiment_split"] == {"positive": 1, "neutral": 2, "negative": 1}
    assert sum(e["sentiment_split"].values()) == e["document_count"]
    assert all(x["names_executive"] for x in e["events"])
    assert e["biggest_drag"]["component"] == "sentiment"      # 0.35/0.75*(100-54.5) is the largest loss
    assert e["low_evidence"] is False and e["stale"] is False


def test_low_evidence_and_stale_flags(env):
    db, _ = env
    c, brand = _client(db)
    p = _person(db, c.id, "Geetika Trehan")
    d = _doc(db, "Geetika Trehan CEO North Zone", brand, p)
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=20)
    _score(db, p, [d], created=old)
    e = ci.search_client_executive(c.id, "Geetika Trehan", db)["executive"]
    assert e["low_evidence"] is True and e["stale"] is True and e["age_days"] >= 19


def test_no_evidence_row_is_never_returned_as_a_zero_score(env):
    db, _ = env
    c, brand = _client(db)
    p = _person(db, c.id, "Karishma Rane")
    d = _doc(db, "Godrej and Karishma Rane", brand, p)
    _score(db, p, [], score=0.0, grade="NA", health="INSUFFICIENT_EVIDENCE")
    e = ci.search_client_executive(c.id, "Karishma Rane", db)["executive"]
    assert e["score"] is None and e["grade"] is None and e["health_status"] == "INSUFFICIENT_EVIDENCE"


def test_tracked_person_without_client_coverage_gets_its_own_status(env):
    db, _ = env
    c, brand = _client(db)
    p = _person(db, c.id, "Nadir Godrej")
    _doc(db, "Nadir Godrej somewhere else", None, p)         # never co-occurs with the brand
    out = ci.search_client_executive(c.id, "Nadir Godrej", db)
    assert out["status"] == "tracked_no_coverage" and out["executive"]["name"] == "Nadir Godrej"
    assert out["client_name"] == c.name


def test_ambiguous_and_candidate_results(env):
    db, _ = env
    c, brand = _client(db)
    _person(db, c.id, "Gaurav Pandey")
    db.add(ExecutiveCandidate(client_id=c.id, name="Gaurav Jain", mention_count=1, confidence=0.75, source_documents=[]))
    db.add(ExecutiveCandidate(client_id=c.id, name="Anil Singhvi", mention_count=2, confidence=0.7, source_documents=[]))
    db.commit()
    amb = ci.search_client_executive(c.id, "Gaurav", db)
    assert amb["status"] == "ambiguous" and amb["total"] == 2
    assert {(n["name"], n["kind"]) for n in amb["names"]} == {("Gaurav Pandey", "tracked"), ("Gaurav Jain", "candidate")}
    cand = ci.search_client_executive(c.id, "anil singhvi", db)
    assert cand["status"] == "unpromoted_candidate" and cand["candidate"]["name"] == "Anil Singhvi"
    assert ci.search_client_executive(c.id, "Pandey", db)["status"] in ("tracked", "tracked_no_coverage")   # one partial match


def test_the_page_no_longer_has_the_provisioning_or_poll_code():
    src = inspect.getsource(ci.search_client_executive)
    for banned in ("provision_entity_search_feeds", "ExecutiveReputationEngine", "RSSFeed", "CollectionJob", "db.add", "db.commit"):
        assert banned not in src


# ---------------------------------------------------------------- /executives is additive
def test_executives_list_carries_as_of(env):
    db, _ = env
    c, brand = _client(db)
    p = _person(db, c.id, "Pirojsha Godrej")
    d = _doc(db, "Pirojsha Godrej", brand, p)
    _score(db, p, [d])
    rows = ci.get_client_executives(c.id, db)
    assert rows[0]["as_of"] and rows[0]["document_count"] == 1 and rows[0]["health_status"] == "PARTIAL"


# ---------------------------------------------------------------- X3: surname rule
def test_surname_rule(env):
    db, eng = env
    c, brand = _client(db, "Godrej Properties")
    pir, nad, muk = _person(db, c.id, "Pirojsha Godrej"), _person(db, c.id, "Nadir Godrej"), _person(db, c.id, "Mukesh Ambani")
    people = [pir, nad, muk]
    assert eng.surname_attach_allowed(db, c.id, "godrej", people) is False      # brand name and shared by two people
    assert eng.surname_attach_allowed(db, c.id, "ambani", people) is True        # unique and not a brand word
    only_one_godrej = [pir, muk]
    assert eng.surname_attach_allowed(db, c.id, "godrej", only_one_godrej) is False   # still the brand name
    two_kumars = [_person(db, c.id, "Ravi Kumar"), _person(db, c.id, "Suraj Kumar")]
    assert eng.surname_attach_allowed(db, c.id, "kumar", two_kumars) is False   # not unique
    assert eng.surname_attach_allowed(db, c.id, "", people) is False


def test_adani_surname_rule(env):
    db, eng = env
    c, brand = _client(db, "Adani Group")
    people = [_person(db, c.id, "Gautam Adani"), _person(db, c.id, "Vinod Adani"), _person(db, c.id, "Mukesh Ambani")]
    assert eng.surname_attach_allowed(db, c.id, "adani", people) is False
    assert eng.surname_attach_allowed(db, c.id, "ambani", people) is True


def test_person_candidate_path_uses_the_surname_rule():
    src = inspect.getsource(ed.EntityDiscoveryEngine._process_person_entity)
    assert "self.surname_attach_allowed(" in src


# ---------------------------------------------------------------- X2: reviewed candidates + single Add
def _cand(db, cid, name, docs, mentions=1, conf=0.6):
    c = ExecutiveCandidate(client_id=cid, name=name, mention_count=mentions, confidence=conf, source_documents=[str(d.id) for d in docs])
    db.add(c)
    db.commit()
    return c


def test_review_ranks_client_related_titled_people_first_and_hides_non_people(env):
    db, eng = env
    c, brand = _client(db, "Adani Group")
    tracked = _person(db, c.id, "Suvendu Adhikari")
    _person(db, c.id, "Gautam Adani")
    d_family = _doc(db, "Gautam Adani has two sons, Karan and Jeet Adani, and the group", brand)
    d_title = _doc(db, "Adani summit: Tata Power chief executive officer Praveer Sinha spoke", brand)
    d_other = _doc(db, "Praveer Sinha elsewhere", None)
    d_plain = _doc(db, "Adani Group stocks: Samir Mehta wealth list", brand)
    _cand(db, c.id, "Samir Mehta", [d_plain], conf=0.6)
    _cand(db, c.id, "Praveer Sinha", [d_title], conf=0.75)
    _cand(db, c.id, "Jeet Adani", [d_family], mentions=2, conf=0.7)
    _cand(db, c.id, "Today Adani", [d_plain], conf=0.6)                 # news fragment
    _cand(db, c.id, "CM Suvendu", [d_plain], conf=0.7)                  # title + first name of a tracked person
    _cand(db, c.id, "Gautam Adani Net Worth", [d_plain], conf=0.5)      # phrase
    _cand(db, c.id, "Realty2026", [d_plain], conf=0.9)                  # digits
    _cand(db, c.id, "Vijaylakshmi Ambala", [d_plain], conf=0.6)
    _cand(db, c.id, "Vijaylaxmi Ambala", [d_plain], conf=0.6)           # spelling twin
    out = eng.review_executive_candidates(db, c.id)
    names = [x["name"] for x in out["candidates"]]
    assert names[0] == "Jeet Adani"                                      # carries the client name and has client documents
    assert names.index("Praveer Sinha") < names.index("Samir Mehta")      # title + client documents before plain
    for hidden in ("Today Adani", "CM Suvendu", "Gautam Adani Net Worth", "Realty2026"):
        assert hidden not in names
    assert sum(1 for n in names if n.startswith("Vijayla")) == 1          # near-duplicates collapse
    assert out["hidden_count"] >= 5
    first = out["candidates"][0]
    assert {"id", "name", "mention_count", "confidence", "client_documents", "title_nearby", "source_document_count"} <= set(first)


def test_add_promotes_exactly_one_candidate_with_no_feeds_or_jobs(env):
    db, eng = env
    c, brand = _client(db)
    d = _doc(db, "Godrej Properties chairman Jane Roe", brand)
    a = _cand(db, c.id, "Jane Roe", [d], mentions=2, conf=0.7)
    b = _cand(db, c.id, "Other Person", [d])
    before = _writes(db)
    out = eng.add_single_executive_candidate(db, c.id, a.id)
    assert out["status"] == "added" and out["message"] == "Added. A score appears once new coverage mentions them."
    after = _writes(db)
    assert after[0] == before[0] + 1 and after[1] == before[1] + 1          # one entity, one keyword
    assert after[2] == before[2] and after[3] == before[3]                  # no feeds, no collection jobs
    ent = db.query(Entity).filter(Entity.name == "Jane Roe").one()
    assert ent.entity_type == "person" and ent.client_id == c.id
    kw = db.query(EntityKeyword).filter(EntityKeyword.entity_id == ent.id).one()
    assert kw.keyword_text == "Jane Roe" and kw.match_type == "exact"
    db.refresh(a), db.refresh(b)
    assert a.promoted_to_executive_id == ent.id and b.promoted_to_executive_id is None   # only the named one
    assert db.query(ExecutiveReputationScore).count() == 0                                # no engine run


def test_add_rejects_duplicates_wrong_client_malformed_and_repeats(env):
    db, eng = env
    c, brand = _client(db)
    other, _ob = _client(db, "Other Co")
    d = _doc(db, "x", brand)
    existing = _person(db, c.id, "Uday Ruddarraju")
    near = _cand(db, c.id, "Uday Ruddaraju", [d])
    glued = _cand(db, c.id, "Nadir GodrejGautam Adani", [d])
    exact = _cand(db, c.id, "uday ruddarraju", [d])
    before = _writes(db)
    assert eng.add_single_executive_candidate(db, c.id, near.id)["status"] == "duplicate"
    assert eng.add_single_executive_candidate(db, c.id, glued.id)["status"] == "rejected"
    assert eng.add_single_executive_candidate(db, other.id, near.id)["status"] == "not_found"   # wrong client
    assert eng.add_single_executive_candidate(db, c.id, uuid.uuid4())["status"] == "not_found"
    assert eng.add_single_executive_candidate(db, c.id, exact.id)["status"] == "already_tracked"
    assert _writes(db)[0] == before[0] and _writes(db)[1] == before[1]
    db.refresh(exact)
    assert exact.promoted_to_executive_id == existing.id
    assert eng.add_single_executive_candidate(db, c.id, exact.id)["status"] == "already_tracked"   # repeat


def test_add_route_does_not_depend_on_the_auto_promotion_switch_and_leaves_bulk_path_off():
    assert ed.EntityDiscoveryConfig.EXECUTIVE_AUTO_PROMOTION_ENABLED is False
    src = inspect.getsource(ci.add_client_executive_candidate)
    assert "promote_executive_candidates" not in src and "calculate_executive_reputation" not in src


# ---------------------------------------------------------------- name shape: real names pass, glued strings do not
@pytest.mark.parametrize("name", ["McDonald Trump", "Thalles DeSouza", "Shaquille O'Neil", "Mary-Ann Joseph", "K. Rammohan Naidu",
                                  "Alexander Skarsgård", "Anne MacArthur", "Leonardo DiCaprio", "Abbe R. Gluck", "Jeffrey Allen Murdock",
                                  "अमित शाह"])
def test_real_name_shapes_are_accepted(env, name):
    db, eng = env
    assert eng.name_shape_error(name) is None
    c, _b = _client(db)
    assert ci.search_client_executive(c.id, name, db)["status"] == "not_found"      # accepted by the shape check, simply unknown


@pytest.mark.parametrize("name", ["Nadir GodrejGautam Adani", "GodrejGautam", "John Smith 3rd", "Realty2026", "<b>Bold</b>", "", "x" * 81, "-Dash Start"])
def test_glued_digits_and_markup_are_rejected(env, name):
    _db, eng = env
    assert eng.name_shape_error(name)


# ---------------------------------------------------------------- Add: refresh, access, ownership, idempotency
def test_add_triggers_the_same_keyword_refresh_the_workers_listen_for(env, monkeypatch):
    db, eng = env
    c, brand = _client(db)
    d = _doc(db, "x", brand)
    a = _cand(db, c.id, "Jane Roe", [d], mentions=2, conf=0.7)
    dup = _cand(db, c.id, "Nadir GodrejGautam Adani", [d])
    events, order = [], []
    import app.utils.redis_client as rc
    import app.services.matching_engine as me
    monkeypatch.setattr(rc.redis_client, "publish", lambda ch, msg: events.append((ch, msg, db.query(Entity).filter(Entity.name == "Jane Roe").count())), raising=False)
    monkeypatch.setattr(me.engine_instance, "refresh_processor", lambda d_: order.append("refresh"))
    out = ci.add_client_executive_candidate(c.id, a.id, db)
    assert out["status"] == "added"
    assert events == [("keyword_updated", "refresh", 1)]       # published once, and only AFTER the entity was committed
    assert order == ["refresh"]
    # nothing is published when nothing was added
    assert ci.add_client_executive_candidate(c.id, dup.id, db)["status"] == "rejected"
    assert ci.add_client_executive_candidate(c.id, a.id, db)["status"] == "already_tracked"
    assert len(events) == 1 and order == ["refresh"]


def test_add_survives_a_redis_or_matcher_failure(env, monkeypatch):
    db, eng = env
    c, brand = _client(db)
    a = _cand(db, c.id, "Jane Roe", [_doc(db, "x", brand)], mentions=2, conf=0.7)
    import app.utils.redis_client as rc
    import app.services.matching_engine as me
    monkeypatch.setattr(rc.redis_client, "publish", lambda *a_: (_ for _ in ()).throw(RuntimeError("redis down")), raising=False)
    monkeypatch.setattr(me.engine_instance, "refresh_processor", lambda d_: (_ for _ in ()).throw(RuntimeError("matcher down")))
    assert ci.add_client_executive_candidate(c.id, a.id, db)["status"] == "added"


def test_the_workers_listener_is_subscribed_to_that_channel():
    import app.core.pubsub as ps
    src = inspect.getsource(ps.redis_listener_thread)
    assert "subscribe('keyword_updated')" in src and "refresh_processor" in src
    assert "publish('keyword_updated', 'refresh')" in inspect.getsource(ci.add_client_executive_candidate)


def test_double_click_creates_exactly_one_entity(env):
    db, eng = env
    c, brand = _client(db)
    a = _cand(db, c.id, "Jane Roe", [_doc(db, "x", brand)], mentions=2, conf=0.7)
    first = eng.add_single_executive_candidate(db, c.id, a.id)
    second = eng.add_single_executive_candidate(db, c.id, a.id)
    third = eng.add_single_executive_candidate(db, c.id, a.id)
    assert (first["status"], second["status"], third["status"]) == ("added", "already_tracked", "already_tracked")
    assert db.query(Entity).filter(Entity.name == "Jane Roe").count() == 1
    assert db.query(EntityKeyword).filter(EntityKeyword.keyword_text == "Jane Roe").count() == 1
    assert "with_for_update" in inspect.getsource(ed.EntityDiscoveryEngine.add_single_executive_candidate)   # concurrent clicks serialise on the row


def test_concurrent_insert_collision_answers_already_tracked_and_adds_nothing_more(env, monkeypatch):
    db, eng = env
    c, brand = _client(db)
    a = _cand(db, c.id, "Jane Roe", [_doc(db, "x", brand)], mentions=2, conf=0.7)
    from sqlalchemy.exc import IntegrityError
    real_flush = db.flush
    state = {"n": 0}

    def flaky_flush(*args, **kw):
        # the first flush that carries the new person Entity collides with a concurrent request's insert
        if state["n"] == 0 and any(isinstance(o, Entity) for o in db.new):
            state["n"] += 1
            db.expunge(next(o for o in list(db.new) if isinstance(o, Entity)))
            raise IntegrityError("insert", {}, Exception("uq_entities_client_name"))
        return real_flush(*args, **kw)
    monkeypatch.setattr(db, "flush", flaky_flush)
    out = eng.add_single_executive_candidate(db, c.id, a.id)
    assert out["status"] == "already_tracked"
    assert db.query(EntityKeyword).count() == 0


@pytest.fixture()
def api(monkeypatch):
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import StaticPool
    from app.core.auth import get_current_user, require_client_access
    from app.core.db import get_db
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    eng = ed.entity_discovery_engine
    monkeypatch.setattr(eng, "_is_valid_person_name_layered", lambda *a, **k: (True, "", ""))
    import app.utils.redis_client as rc
    import app.services.matching_engine as me
    monkeypatch.setattr(rc.redis_client, "publish", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(me.engine_instance, "refresh_processor", lambda d_: None)
    user = User(id=uuid.uuid4(), email="u@test.test", password_hash="x", role=ROLE_CLIENT_USER)
    db.add(user)
    db.commit()
    app = FastAPI()
    # same composition as app/main.py: login + require_client_access on the whole client-intelligence router
    app.include_router(ci.router, prefix="/client-intelligence", dependencies=[Depends(get_current_user), Depends(require_client_access)])
    app.dependency_overrides[get_current_user] = lambda: db.query(User).filter(User.id == user.id).one()
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app), db, user
    db.close()


def test_main_mounts_the_router_behind_login_and_per_client_access():
    src = open(os.path.join(os.path.dirname(__file__), "..", "app", "main.py"), encoding="utf-8").read()
    assert "_auth_and_client = _auth + [Depends(require_client_access)]" in src
    assert 'client_intelligence.router, prefix="/client-intelligence", tags=["client_intelligence"], dependencies=_auth_and_client' in src


def test_add_endpoint_enforces_per_client_access_and_candidate_ownership(api):
    http, db, user = api
    mine, mine_brand = _client(db, "Mine Co")
    theirs, their_brand = _client(db, "Theirs Co")
    db.add(UserClientAccess(user_id=user.id, client_id=mine.id))
    db.commit()
    own = _cand(db, mine.id, "Jane Roe", [_doc(db, "x", mine_brand)], mentions=2, conf=0.7)
    foreign = _cand(db, theirs.id, "Other Person", [_doc(db, "y", their_brand)], mentions=2, conf=0.7)
    before = _writes(db)

    # a client the user may not access: refused before anything runs, for every executive route
    assert http.post(f"/client-intelligence/{theirs.id}/executive-candidates/{foreign.id}/add").status_code == 403
    assert http.get(f"/client-intelligence/{theirs.id}/executive-candidates-reviewed").status_code == 403
    assert http.get(f"/client-intelligence/{theirs.id}/executive-search", params={"name": "Other Person"}).status_code == 403
    assert _writes(db) == before

    # an accessible client but another client's candidate id: nothing happens
    r = http.post(f"/client-intelligence/{mine.id}/executive-candidates/{foreign.id}/add")
    assert r.status_code == 200 and r.json()["status"] == "not_found"
    assert _writes(db) == before
    db.refresh(foreign)
    assert foreign.promoted_to_executive_id is None

    # the happy path, and a double click over HTTP
    ok = http.post(f"/client-intelligence/{mine.id}/executive-candidates/{own.id}/add")
    again = http.post(f"/client-intelligence/{mine.id}/executive-candidates/{own.id}/add")
    assert ok.json()["status"] == "added" and ok.json()["message"] == "Added. A score appears once new coverage mentions them."
    assert again.json()["status"] == "already_tracked"
    assert db.query(Entity).filter(Entity.client_id == mine.id, Entity.entity_type == "person").count() == 1


def test_super_admin_reaches_any_client_and_a_missing_client_is_404(api):
    http, db, user = api
    user.role = ROLE_SUPER_ADMIN
    db.commit()
    c, brand = _client(db)
    cand = _cand(db, c.id, "Jane Roe", [_doc(db, "x", brand)], mentions=2, conf=0.7)
    assert http.post(f"/client-intelligence/{c.id}/executive-candidates/{cand.id}/add").json()["status"] == "added"
    assert http.post(f"/client-intelligence/{uuid.uuid4()}/executive-candidates/{cand.id}/add").status_code == 404


# ---------------------------------------------------------------- reviewed list: constant number of queries
def _count_statements(db, fn):
    from sqlalchemy import event
    bind = db.get_bind()
    seen = []

    def listener(conn, cur, stmt, params, ctx, many):
        seen.append(stmt)
    event.listen(bind, "before_cursor_execute", listener)
    try:
        fn()
    finally:
        event.remove(bind, "before_cursor_execute", listener)
    return len(seen)


def test_reviewed_candidates_use_a_constant_number_of_queries(env):
    db, eng = env
    c, brand = _client(db, "Adani Group")
    _person(db, c.id, "Gautam Adani")
    docs = [_doc(db, f"Adani Group chief executive officer Person{i} spoke at the summit {i}", brand) for i in range(3)]

    def make(n, start):
        for i in range(n):
            _cand(db, c.id, f"Firstname{chr(97 + (start + i) % 26)}x Lastname{chr(97 + ((start + i) // 26) % 26)}y",
                  [docs[i % 3]], mentions=1, conf=0.6)
    make(3, 0)
    few = _count_statements(db, lambda: eng.review_executive_candidates(db, c.id))
    make(40, 3)
    many = _count_statements(db, lambda: eng.review_executive_candidates(db, c.id))
    assert many == few                      # no per-candidate query
    assert many <= 12
    out = eng.review_executive_candidates(db, c.id)
    assert len(out["candidates"]) + out["hidden_count"] == 43


def test_the_in_memory_title_rule_matches_the_promotion_rule(env):
    db, eng = env
    for text, name, expected in [
        ("Acme chairman Jane Roe said profits rose", "Jane Roe", True),
        ("Jane Roe wrote a poem about spring", "Jane Roe", False),
        ("Orris MD", "Orris MD", False),
    ]:
        assert eng._title_near_name(text, name) is expected


# ---------------------------------------------------------------- review: organisations/places hidden, client-linked titled people first
def test_review_hides_organisations_places_holidays_and_filler_fragments(env):
    db, eng = env
    c, brand = _client(db, "Adani Group")
    d = _doc(db, "Adani Group news about many things", brand)
    for bad in ["Tata Sons", "Ambuja Cements", "Balaji Wafers", "Vishakha Renewables", "Delhi NCR", "Tamil Nadu", "Gandhi Jayanti",
                "Sarjapur Road", "Evora Estate", "Apni Baat", "Ke Saath", "Aapke Safar Ke Humsafar", "Realty Sector", "Balaji Wafers Sells",
                "Lodha Acquire", "Power Mech", "Max Enviro", "Ganesh Benzoplast"]:
        _cand(db, c.id, bad, [d], conf=0.8)
    _cand(db, c.id, "Jeet Adani", [d], mentions=2, conf=0.7)
    _cand(db, c.id, "K Rammohan Naidu", [d], conf=0.5)
    out = eng.review_executive_candidates(db, c.id)
    names = [x["name"] for x in out["candidates"]]
    assert "Jeet Adani" in names and "K Rammohan Naidu" in names
    assert len(names) == 2 and out["hidden_count"] == 18


def test_review_puts_titled_people_next_to_the_client_before_other_companies_people(env):
    db, eng = env
    c, brand = _client(db, "Godrej Properties")
    d_client = _doc(db, "Nyrika Holkar, executive director, Godrej Enterprises Group, elaborates that the growth potential is large")   # no brand mention row
    d_other = _doc(db, "Tata Realty appoints Gaurav Jain as MD and CEO", None)
    d_plain = _doc(db, "Godrej Properties share analysis with Anil Singhvi", brand)
    _cand(db, c.id, "Gaurav Jain", [d_other], conf=0.75)
    _cand(db, c.id, "Anil Singhvi", [d_plain], mentions=2, conf=0.7)
    _cand(db, c.id, "Nyrika Holkar", [d_client], conf=0.75)
    names = [x["name"] for x in eng.review_executive_candidates(db, c.id)["candidates"]]
    assert names[0] == "Nyrika Holkar"                       # title + the client's name next to hers
    assert names.index("Anil Singhvi") < names.index("Gaurav Jain")   # client-related documents beat none
    nyrika = next(x for x in eng.review_executive_candidates(db, c.id)["candidates"] if x["name"] == "Nyrika Holkar")
    assert nyrika["client_documents"] == 1 and nyrika["title_nearby"] is True


def test_add_takes_the_same_advisory_lock_scheme_as_candidate_discovery_and_links_on_collision():
    src = inspect.getsource(ed.EntityDiscoveryEngine.add_single_executive_candidate)
    assert "pg_advisory_xact_lock" in src and "with_for_update" in src
    assert "winner" in src       # a unique-name collision links the candidate to the entity that won
