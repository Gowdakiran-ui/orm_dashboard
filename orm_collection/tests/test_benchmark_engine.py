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
from app.models.competitor_benchmark import CompetitorBenchmark
from app.services.intelligence.benchmark_engine import BenchmarkEngine

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

def setup_entities(db):
    client_id = uuid.uuid4()
    client = Client(id=client_id, name="Benchmark Test Client")
    db.add(client)
    
    # Client Entity (Brand)
    e_brand = Entity(id=uuid.uuid4(), client_id=client_id, name="My Brand", entity_type="brand")
    db.add(e_brand)
    
    # Competitor 1 (Strong Competitor)
    e_comp1 = Entity(id=uuid.uuid4(), client_id=client_id, name="Strong Competitor", entity_type="competitor")
    db.add(e_comp1)
    
    # Competitor 2 (Weak Competitor)
    e_comp2 = Entity(id=uuid.uuid4(), client_id=client_id, name="Weak Competitor", entity_type="competitor")
    db.add(e_comp2)
    
    db.commit()
    
    # Docs for Brand
    for _ in range(50):
        d_id = uuid.uuid4()
        db.add(Document(id=d_id, url=f"http://test.com/{d_id}", normalized_content="brand"))
        db.add(EntityMention(document_id=d_id, entity_id=e_brand.id, mention_count=10)) # 500 mentions total
        db.add(DocumentSentiment(document_id=d_id, sentiment_score=0.8, confidence_score=1.0, weighted_sentiment_score=0.8, sentiment_label="Positive"))
        db.add(RiskEvent(client_id=client_id, entity_id=e_brand.id, document_id=d_id, risk_score=10.0, risk_level="LOW"))
        
    # Docs for Comp1
    for _ in range(30):
        d_id = uuid.uuid4()
        db.add(Document(id=d_id, url=f"http://test.com/{d_id}", normalized_content="comp1"))
        db.add(EntityMention(document_id=d_id, entity_id=e_comp1.id, mention_count=10)) # 300 mentions total
        db.add(DocumentSentiment(document_id=d_id, sentiment_score=0.5, confidence_score=1.0, weighted_sentiment_score=0.5, sentiment_label="Positive"))
        db.add(RiskEvent(client_id=client_id, entity_id=e_comp1.id, document_id=d_id, risk_score=30.0, risk_level="MEDIUM"))
        
    # Docs for Comp2
    for _ in range(20):
        d_id = uuid.uuid4()
        db.add(Document(id=d_id, url=f"http://test.com/{d_id}", normalized_content="comp2"))
        db.add(EntityMention(document_id=d_id, entity_id=e_comp2.id, mention_count=10)) # 200 mentions total
        db.add(DocumentSentiment(document_id=d_id, sentiment_score=-0.8, confidence_score=1.0, weighted_sentiment_score=-0.8, sentiment_label="Negative"))
        db.add(RiskEvent(client_id=client_id, entity_id=e_comp2.id, document_id=d_id, risk_score=90.0, risk_level="CRITICAL"))
        
    db.commit()
    return client_id, e_brand.id, e_comp1.id, e_comp2.id

@pytest.mark.xfail(
    reason="SQLite test harness incompatible with benchmark_engine.py's real "
           "Postgres-specific upsert: it compiles ON CONFLICT (uq_competitor_benchmark_run) "
           "using a named constraint, which SQLite's ON CONFLICT only accepts as a "
           "column list, not a constraint name -- sqlite3.OperationalError: 'no such "
           "column: uq_competitor_benchmark_run'. Not a production bug (real DB is "
           "Postgres); needs a real/test Postgres DB to validate this scenario, out "
           "of scope for this phase (FINDINGS.md Phase 11 #38).",
    strict=False,
)
def test_validation():
    print("Setting up mock database for Benchmark Engine...")
    db = Session()
    try:
        client_id, e_brand, e_comp1, e_comp2 = setup_entities(db)
        
        engine_svc = BenchmarkEngine()
        
        print("Running Benchmark Engine Inference...")
        start_time = time.time()
        
        # Test latency and correctness
        engine_svc.calculate_competitor_benchmarks(db, client_id)
        
        # Throughput test
        for _ in range(99): # Total 100 iterations
            engine_svc.calculate_competitor_benchmarks(db, client_id)
            
        exec_time = time.time() - start_time
        avg_time = exec_time / 100.0
        throughput = 100.0 / exec_time if exec_time > 0 else 0
        print(f"Performance Metric: {avg_time:.4f}s avg per client ({throughput:.1f} clients/sec throughput per worker)")

        benchmarks = db.query(CompetitorBenchmark).filter(CompetitorBenchmark.client_id == client_id).all()

        b_comp1 = next((b for b in benchmarks if b.competitor_entity_id == e_comp1), None)
        b_comp2 = next((b for b in benchmarks if b.competitor_entity_id == e_comp2), None)

        # Brand: Rep=90, Mentions=500, SOV=50%
        # Comp1: Rep=72.5, Mentions=300, SOV=30%
        # Comp2: Rep=10, Mentions=200, SOV=20%

        assert b_comp1 and b_comp2, "Both competitor benchmarks must exist"
        assert b_comp1.rank < b_comp2.rank, f"Reputation Ranking: comp1.rank ({b_comp1.rank}) should be < comp2.rank ({b_comp2.rank})"
        assert b_comp1.sentiment_score > b_comp2.sentiment_score, "Sentiment Ranking: comp1 should rank above comp2"
        assert b_comp1.risk_score < b_comp2.risk_score, "Risk Ranking: comp1 should have lower risk than comp2"
        assert abs(b_comp1.share_of_voice - 30.0) < 1.0 and abs(b_comp2.share_of_voice - 20.0) < 1.0, \
            f"Share Of Voice Calculation: comp1 sov={b_comp1.share_of_voice}, comp2 sov={b_comp2.share_of_voice}"
        assert b_comp1.top_narrative is not None, "Narrative Comparison: comp1.top_narrative should not be None"

    finally:
        db.close()

if __name__ == "__main__":
    test_validation()
