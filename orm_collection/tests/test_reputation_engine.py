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
from app.models.sentiment import DocumentSentiment
from app.models.risk import RiskEvent
from app.models.trends import TrendEvent
from app.models.narrative import Narrative
from app.models.reputation import ReputationScore
from app.services.intelligence.reputation_engine import ReputationEngine

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

def setup_client(db, name, avg_sentiment, risk_score, mentions, narrative_sentiment, trend_type):
    client_id = uuid.uuid4()
    client = Client(id=client_id, name=name)
    db.add(client)
    
    entity_id = uuid.uuid4()
    entity = Entity(id=entity_id, client_id=client_id, name=f"{name} Entity")
    db.add(entity)
    
    # Docs & Mentions
    for i in range(5):
        doc_id = uuid.uuid4()
        db.add(Document(id=doc_id, url=f"http://test.com/{doc_id}", normalized_content="test"))
        db.add(EntityMention(document_id=doc_id, entity_id=entity_id, mention_count=mentions // 5))
        db.add(DocumentSentiment(document_id=doc_id, sentiment_score=avg_sentiment, confidence_score=1.0, weighted_sentiment_score=avg_sentiment, sentiment_label="Neutral"))
        db.add(RiskEvent(client_id=client_id, document_id=doc_id, risk_score=risk_score, risk_level="HIGH"))
    
    # Narrative
    db.add(Narrative(client_id=client_id, narrative_name="Test Narrative", narrative_type="General", mention_count=mentions, sentiment_score=narrative_sentiment, status="PEAK"))
    
    # Trend
    if trend_type == "GOOD":
        db.add(TrendEvent(client_id=client_id, trend_type="Topic", percentage_change=50.0, severity="HIGH"))
    elif trend_type == "BAD":
        db.add(TrendEvent(client_id=client_id, trend_type="Sentiment", percentage_change=80.0, severity="CRITICAL"))
        
    db.commit()
    return client_id

@pytest.mark.xfail(
    reason="SQLite test harness incompatible with reputation_engine.py's real "
           "Postgres-specific upsert: it compiles ON CONFLICT (uq_client_reputation_run) "
           "using a named constraint, which SQLite's ON CONFLICT only accepts as a "
           "column list, not a constraint name -- sqlite3.OperationalError: 'no such "
           "column: uq_client_reputation_run'. Not a production bug (real DB is "
           "Postgres); needs a real/test Postgres DB to validate this scenario, out "
           "of scope for this phase (FINDINGS.md Phase 11 #38).",
    strict=False,
)
def test_validation():
    print("Setting up mock database for Reputation Engine...")
    db = Session()
    try:
        # 1. Strong Positive Brand Scenario
        # Sentiment=0.8, Risk=10, High Mentions=2000, Positive Narrative=0.8, Good Trend
        client_pos = setup_client(db, "Positive Brand", 0.8, 10.0, 2000, 0.8, "GOOD")
        
        # 2. Neutral Brand Scenario
        # Sentiment=0.0, Risk=40, Med Mentions=500, Neutral Narrative=0.0, No Trend
        client_neu = setup_client(db, "Neutral Brand", 0.0, 40.0, 500, 0.0, "NONE")
        
        # 3. High Risk Negative Brand Scenario
        # Sentiment=-0.9, Risk=90, Mentions=1500, Negative Narrative=-0.9, Bad Trend
        client_neg = setup_client(db, "Negative Brand", -0.9, 90.0, 1500, -0.9, "BAD")
        
        engine_svc = ReputationEngine()
        
        print("Running Reputation Engine Inference...")
        start_time = time.time()
        
        # Test latency and correctness
        engine_svc.calculate_reputation_score(db, client_pos)
        engine_svc.calculate_reputation_score(db, client_neu)
        engine_svc.calculate_reputation_score(db, client_neg)
        
        # Throughput test
        for _ in range(97): # Total 100 iterations
            engine_svc.calculate_reputation_score(db, client_pos)
            
        exec_time = time.time() - start_time
        avg_time = exec_time / 100.0
        throughput = 100.0 / exec_time if exec_time > 0 else 0
        print(f"Performance Metric: {avg_time:.4f}s avg per client ({throughput:.1f} clients/sec throughput per worker)")

        rep_pos = db.query(ReputationScore).filter(ReputationScore.client_id == client_pos).order_by(ReputationScore.created_at.desc()).first()
        rep_neu = db.query(ReputationScore).filter(ReputationScore.client_id == client_neu).order_by(ReputationScore.created_at.desc()).first()
        rep_neg = db.query(ReputationScore).filter(ReputationScore.client_id == client_neg).order_by(ReputationScore.created_at.desc()).first()

        assert rep_pos and rep_pos.grade in ["A", "A+"], f"Strong Positive Brand Scenario: expected A/A+, got {rep_pos.grade if rep_pos else None}"
        assert rep_neu and rep_neu.grade in ["B", "C"], f"Neutral Brand Scenario: expected B/C, got {rep_neu.grade if rep_neu else None}"
        assert rep_neg and rep_neg.grade in ["D", "F"], f"High Risk Negative Brand Scenario: expected D/F, got {rep_neg.grade if rep_neg else None}"

    finally:
        db.close()

if __name__ == "__main__":
    test_validation()
