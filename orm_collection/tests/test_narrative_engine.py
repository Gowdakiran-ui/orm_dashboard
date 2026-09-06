import time
import sys
import os
import uuid
import datetime
import pytest

# Add the app to path so we can import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.document import Document
from app.models.topic import Topic, DocumentTopic
from app.models.sentiment import DocumentSentiment
from app.models.risk import RiskEvent
from app.models.trends import TrendEvent
from app.models.narrative import Narrative
from app.services.intelligence.narrative_engine import NarrativeEngine

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import JSONB

@compiles(PG_UUID, 'sqlite')
def compile_uuid(element, compiler, **kw):
    return "CHAR(32)"

@compiles(JSONB, 'sqlite')
def compile_jsonb(element, compiler, **kw):
    return "TEXT"

engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def create_documents_for_topic(db, client_id, entity_id, topic_name, doc_count, sentiment_score, risk_score, trend_pct):
    topic_id = uuid.uuid4()
    topic = Topic(id=topic_id, name=topic_name, is_active=True)
    db.add(topic)
    
    docs = []
    for _ in range(doc_count):
        doc_id = uuid.uuid4()
        doc = Document(id=doc_id, url=f"http://test.com/{doc_id}", normalized_content="test")
        db.add(doc)
        
        db.add(EntityMention(document_id=doc_id, entity_id=entity_id, mention_count=1))
        db.add(DocumentTopic(document_id=doc_id, topic_id=topic_id, confidence_score=1.0))
        db.add(DocumentSentiment(document_id=doc_id, sentiment_score=sentiment_score, confidence_score=1.0, sentiment_label="Negative", weighted_sentiment_score=sentiment_score))
        db.add(RiskEvent(client_id=client_id, document_id=doc_id, risk_score=risk_score, risk_level="HIGH"))
        
        docs.append(doc_id)
        
    db.add(TrendEvent(client_id=client_id, topic_id=topic_id, trend_type="Topic", percentage_change=trend_pct, severity="HIGH"))
    db.commit()

@pytest.mark.xfail(
    reason="The Document.created_at AttributeError this test originally caught "
           "(narrative_engine.py ~348/~358) is fixed -- confirmed by re-running: "
           "zero AttributeErrors, execution now completes the full loop. It still "
           "can't pass end-to-end because of a separate, already-documented issue: "
           "SQLite test harness incompatible with narrative_engine.py's real "
           "Postgres-specific upsert (ON CONFLICT (uq_client_narrative) using a "
           "named constraint, which SQLite's ON CONFLICT only accepts as a column "
           "list) -- same class of gap as test_benchmark_engine.py/"
           "test_reputation_engine.py (FINDINGS.md Phase 11 #38). Not a production "
           "bug; needs a real/test Postgres DB to validate, out of scope here.",
    strict=False,
)
def test_validation():
    print("Setting up mock database for Narrative Engine...")
    db = Session()
    try:
        client_id = uuid.uuid4()
        client = Client(id=client_id, name="Test Client")
        db.add(client)
        
        entity_id = uuid.uuid4()
        entity = Entity(id=entity_id, client_id=client_id, name="Test Entity")
        db.add(entity)
        db.commit()

        # Scenarios
        # 1. Layoff Narrative (EMERGING)
        create_documents_for_topic(db, client_id, entity_id, "Layoffs", 10, -0.8, 60.0, 5.0)
        
        # 2. Customer Complaint Narrative (GROWING)
        create_documents_for_topic(db, client_id, entity_id, "Customer Complaints", 20, -0.6, 40.0, 60.0)
        
        # 3. Cybersecurity Narrative (PEAK)
        create_documents_for_topic(db, client_id, entity_id, "Cybersecurity", 60, -0.9, 90.0, 20.0)
        
        # 4. Regulatory Narrative (DECLINING)
        create_documents_for_topic(db, client_id, entity_id, "Regulatory Action", 15, -0.5, 50.0, -20.0)
        
        engine_svc = NarrativeEngine()
        
        print("Running Narrative Engine Inference...")
        start_time = time.time()
        
        # Test latency and correctness
        engine_svc.calculate_narratives(db, client_id)
        
        # Throughput test
        for _ in range(99): # Total 100 iterations
            engine_svc.calculate_narratives(db, client_id)
            
        exec_time = time.time() - start_time
        avg_time = exec_time / 100.0
        throughput = 100.0 / exec_time if exec_time > 0 else 0
        print(f"Performance Metric: {avg_time:.4f}s avg per client ({throughput:.1f} clients/sec throughput per worker)")

        narratives = db.query(Narrative).filter(Narrative.client_id == client_id).all()

        # Checks
        has_layoff = False
        has_cust = False
        has_cyber = False
        has_reg = False
        status_pass = True
        agg_pass = True

        for n in narratives:
            if n.narrative_name == "Layoff Narrative":
                has_layoff = True
                if n.status != "EMERGING": status_pass = False
                if n.mention_count != 10: agg_pass = False
            elif n.narrative_name == "Customer Dissatisfaction Narrative":
                has_cust = True
                if n.status != "GROWING": status_pass = False
            elif n.narrative_name == "Cybersecurity Risk Narrative":
                has_cyber = True
                if n.status != "PEAK": status_pass = False
                if n.risk_score != 90.0: agg_pass = False
            elif n.narrative_name == "Regulatory Scrutiny Narrative":
                has_reg = True
                if n.status != "DECLINING": status_pass = False

        assert has_layoff, "Layoff Narrative Detection: 'Layoff Narrative' was not generated"
        assert has_cust, "Customer Complaint Narrative Detection: 'Customer Dissatisfaction Narrative' was not generated"
        assert has_cyber, "Cybersecurity Narrative Detection: 'Cybersecurity Risk Narrative' was not generated"
        assert has_reg, "Regulatory Narrative Detection: 'Regulatory Scrutiny Narrative' was not generated"
        assert status_pass, "Narrative Status Calculation: one or more narratives has the wrong status"
        assert agg_pass, "Narrative Aggregation Accuracy: mention_count/risk_score aggregation is wrong"

    finally:
        db.close()


# --- _rank_prominent_persons -------------------------------------------
#
# Tested directly against lightweight mocks rather than through the full
# calculate_narratives() pipeline above: that method can't complete
# end-to-end in this SQLite test harness for an unrelated, already-
# documented reason (the xfail above -- Postgres-specific
# ON CONFLICT (uq_client_narrative) upsert), and _rank_prominent_persons
# itself does no DB I/O -- it only reads the mention_map/risk_map dicts
# calculate_narratives() already preloaded, so it doesn't need that
# harness at all.

class _FakeEntity:
    def __init__(self, entity_id, name, entity_type="person"):
        self.entity_id = entity_id
        self.name = name
        self.entity_type = entity_type


class _FakeMention:
    def __init__(self, entity):
        self.entity_id = entity.entity_id
        self.entity = entity


class _FakeRiskEvent:
    def __init__(self, entity_id, role_classification):
        self.entity_id = entity_id
        self.explainability = {"role_classification": role_classification}


def test_rank_prominent_persons_excludes_pure_bystander():
    """
    The real bug this fix closes: a Tesla executive (modeled here as
    'Thomas Edison') promoted off a single incidental mention, classified
    BYSTANDER in the one document he appears in, previously still showed
    up as the narrative's own top theme owner. Must be excluded entirely
    now -- zero non-bystander documents is zero evidence of driving the
    story.
    """
    engine_svc = NarrativeEngine()
    edison = _FakeEntity(uuid.uuid4(), "Thomas Edison")
    doc_id = uuid.uuid4()

    mention_map = {doc_id: [_FakeMention(edison)]}
    risk_map = {doc_id: [_FakeRiskEvent(edison.entity_id, "BYSTANDER")]}

    ranked = engine_svc._rank_prominent_persons([doc_id], mention_map, risk_map)

    assert edison.entity_id not in [r[0] for r in ranked], (
        "Thomas Edison (pure bystander, 1 mention) must not appear in the "
        "key-entities list at all"
    )


def test_rank_prominent_persons_ranks_genuine_protagonist_first():
    """
    Guard against the mirror-image bug the task explicitly calls out:
    someone genuinely central to a narrative, appearing across several
    articles, must still rank at the top -- not get wrongly excluded or
    outranked by a low-volume incidental mention.
    """
    engine_svc = NarrativeEngine()
    protagonist = _FakeEntity(uuid.uuid4(), "Elon Musk")
    bystander = _FakeEntity(uuid.uuid4(), "Thomas Edison")
    doc_ids = [uuid.uuid4() for _ in range(4)]

    # Protagonist is SELF (i.e. not classified as bystander/exonerated --
    # role=None here, matching a document whose score never triggered
    # risk_engine.py's LLM gate, treated as non-bystander) in all 4 articles.
    mention_map = {did: [_FakeMention(protagonist)] for did in doc_ids}
    risk_map = {did: [_FakeRiskEvent(protagonist.entity_id, None)] for did in doc_ids}

    # Bystander appears once, in the same cluster, classified BYSTANDER.
    mention_map[doc_ids[0]].append(_FakeMention(bystander))
    risk_map[doc_ids[0]].append(_FakeRiskEvent(bystander.entity_id, "BYSTANDER"))

    ranked = engine_svc._rank_prominent_persons(doc_ids, mention_map, risk_map)
    ranked_ids = [r[0] for r in ranked]

    assert protagonist.entity_id in ranked_ids, "Genuine 4-article protagonist must still be ranked"
    assert ranked_ids[0] == protagonist.entity_id, "Genuine protagonist must rank above a 1-mention bystander"
    assert bystander.entity_id not in ranked_ids, "Pure bystander must still be excluded even alongside a real protagonist"


def test_rank_prominent_persons_mixed_role_ranks_by_ratio_not_excluded():
    """
    Someone who is the actual subject in some articles and a bystander in
    others (e.g. a wire-copy republish of the same story) must be kept and
    ranked by the ratio -- not excluded outright just because one of their
    mentions was a bystander occurrence.
    """
    engine_svc = NarrativeEngine()
    mixed = _FakeEntity(uuid.uuid4(), "Mixed Role Exec")
    doc_ids = [uuid.uuid4() for _ in range(4)]

    mention_map = {did: [_FakeMention(mixed)] for did in doc_ids}
    risk_map = {
        doc_ids[0]: [_FakeRiskEvent(mixed.entity_id, "SELF")],
        doc_ids[1]: [_FakeRiskEvent(mixed.entity_id, "SELF")],
        doc_ids[2]: [_FakeRiskEvent(mixed.entity_id, "SELF")],
        doc_ids[3]: [_FakeRiskEvent(mixed.entity_id, "BYSTANDER")],
    }

    ranked = engine_svc._rank_prominent_persons(doc_ids, mention_map, risk_map)

    assert len(ranked) == 1
    entity_id, name, prominence, non_bystander_count, total = ranked[0]
    assert entity_id == mixed.entity_id
    assert non_bystander_count == 3 and total == 4
    assert prominence == pytest.approx(0.75)


if __name__ == "__main__":
    test_validation()
