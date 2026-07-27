import sys
import os
import time
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.document import Document
from app.models.topic import Topic, DocumentTopic
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.risk import RiskEvent
from app.models.narrative import Narrative
from app.models.reputation import ReputationScore
from app.models.competitor_benchmark import CompetitorBenchmark
from app.services.intelligence.narrative_engine import NarrativeEngine
from app.services.intelligence.reputation_engine import ReputationEngine
from app.services.intelligence.benchmark_engine import BenchmarkEngine

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID

@compiles(UUID, 'sqlite')
def compile_uuid_sqlite(type_, compiler, **kw):
    return 'VARCHAR(36)'

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

# Global tracking
client_ids = []

topics = []

def seed_db(num_clients):
    print(f"Seeding {num_clients} clients...")
    global client_ids, topics
    if not topics:
        topics = [Topic(id=uuid.uuid4(), name=f"Topic_{i}") for i in range(5)]
        db.add_all(topics)
        db.commit()

    docs = []
    mentions = []
    doc_topics = []
    doc_sentiments = []
    risks = []
    
    for c in range(num_clients):
        c_id = uuid.uuid4()
        client_ids.append(c_id)
        db.add(Client(id=c_id, name=f"Client_{c}"))
        
        # 2 Entities per client
        e1_id, e2_id = uuid.uuid4(), uuid.uuid4()
        db.add_all([
            Entity(id=e1_id, client_id=c_id, name=f"Brand_{c}", entity_type="brand"),
            Entity(id=e2_id, client_id=c_id, name=f"Comp_{c}", entity_type="competitor")
        ])
        
        # 10 Documents per client
        for d in range(10):
            d_id = uuid.uuid4()
            docs.append(Document(id=d_id, url=f"http://test.com/{c_id}/{d}", source_id=uuid.uuid4(), title="Test", normalized_content="Test"))
            
            # Mentions
            mentions.append(EntityMention(document_id=d_id, entity_id=e1_id if d % 2 == 0 else e2_id))
            
            # Topics
            doc_topics.append(DocumentTopic(document_id=d_id, topic_id=topics[d % 5].id, confidence_score=0.9))
            
            # Sentiment
            doc_sentiments.append(DocumentSentiment(
                document_id=d_id,
                sentiment_label="Positive",
                sentiment_score=0.5,
                confidence_score=0.9,
                weighted_sentiment_score=0.5
            ))
            
            db.add(EntitySentiment(
                document_id=d_id,
                entity_id=e1_id if d % 2 == 0 else e2_id,
                sentiment_label="Positive",
                sentiment_score=0.5,
                confidence_score=0.9
            ))
            risks.append(RiskEvent(client_id=c_id, document_id=d_id, entity_id=e1_id, risk_score=50, risk_level="MEDIUM"))
            
    # Bulk insert for speed
    db.bulk_save_objects(docs)
    db.bulk_save_objects(mentions)
    db.bulk_save_objects(doc_topics)
    db.bulk_save_objects(doc_sentiments)
    db.bulk_save_objects(risks)
    db.commit()
    print("Seeding complete.")

def run_tests():
    narrative_engine = NarrativeEngine()
    reputation_engine = ReputationEngine()
    benchmark_engine = BenchmarkEngine()
    
    metrics = []
    for test_size in [10, 90, 400, 500]: # Cumulative sizes to reach 10, 100, 500, 1000 total
        seed_db(test_size)
        total_clients = len(client_ids)
        print(f"--- Testing {total_clients} Clients ---")
        
        # We only measure the time it takes to run for a sample client (or all clients to see the scale)
        # Let's run for ALL clients to measure total system scaling impact
        
        # Narrative
        start = time.time()
        for cid in client_ids:
            narrative_engine.calculate_narratives(db, cid)
        n_time = time.time() - start
        
        # Reputation
        start = time.time()
        for cid in client_ids:
            reputation_engine.calculate_reputation_score(db, cid)
        r_time = time.time() - start
        
        # Benchmark
        start = time.time()
        for cid in client_ids:
            benchmark_engine.calculate_competitor_benchmarks(db, cid)
        b_time = time.time() - start
        
        metrics.append({
            "clients": total_clients,
            "narrative_time": n_time,
            "reputation_time": r_time,
            "benchmark_time": b_time
        })
        
    return metrics

def inject_optimizations():
    print("Injecting Composite Indexes...")
    # Composite indexes based on engine joins
    db.execute(text("CREATE INDEX idx_entmention_doc_ent ON entity_mentions(document_id, entity_id)"))
    db.execute(text("CREATE INDEX idx_entity_client_type ON entities(client_id, entity_type)"))
    db.execute(text("CREATE INDEX idx_doctopic_doc_top ON document_topics(document_id, topic_id)"))
    db.execute(text("CREATE INDEX idx_docs_client_id ON document_sentiment(document_id, entity_id)"))
    db.commit()

if __name__ == "__main__":
    print("=== BEFORE OPTIMIZATION ===")
    before_metrics = run_tests()
    
    # Reset DB
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    client_ids = []
    topics = []
    
    inject_optimizations()
    
    print("\n=== AFTER OPTIMIZATION ===")
    after_metrics = run_tests()
    
    print("\n=== RESULTS ===")
    print("Clients | Nar(B) | Rep(B) | Ben(B) || Nar(A) | Rep(A) | Ben(A)")
    for i in range(4):
        b = before_metrics[i]
        a = after_metrics[i]
        print(f"{b['clients']:7} | {b['narrative_time']:6.2f} | {b['reputation_time']:6.2f} | {b['benchmark_time']:6.2f} || {a['narrative_time']:6.2f} | {a['reputation_time']:6.2f} | {a['benchmark_time']:6.2f}")
