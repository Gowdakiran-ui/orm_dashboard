import time
import sys
import os
import uuid
import datetime

# Add the app to path so we can import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.db import Base
from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.document import Document
from app.models.topic import Topic, DocumentTopic
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.trends import TrendEvent
from app.models.risk import RiskEvent
from app.services.intelligence.risk_engine import RiskEngine

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

def create_scenario(db, client_id, topic_name, sentiment, trend_severity):
    entity_id = uuid.uuid4()
    entity = Entity(id=entity_id, client_id=client_id, name=f"Test Entity {topic_name}")
    db.add(entity)

    doc_id = uuid.uuid4()
    doc = Document(id=doc_id, url=f"http://test.com/{doc_id}", normalized_content="test")
    db.add(doc)
    
    topic_id = uuid.uuid4()
    topic = Topic(id=topic_id, name=topic_name, is_active=True)
    db.add(topic)
    
    db.add(EntityMention(document_id=doc_id, entity_id=entity_id, mention_count=1))
    db.add(DocumentTopic(document_id=doc_id, topic_id=topic_id, confidence_score=1.0))
    
    # Add sentiment
    db.add(DocumentSentiment(document_id=doc_id, sentiment_label=sentiment, sentiment_score=1.0, confidence_score=1.0, weighted_sentiment_score=1.0))
    db.add(EntitySentiment(document_id=doc_id, entity_id=entity_id, sentiment_label=sentiment, sentiment_score=1.0, confidence_score=1.0))
    
    if trend_severity:
        db.add(TrendEvent(client_id=client_id, entity_id=entity_id, trend_type="Mention", percentage_change=100.0, severity=trend_severity))
        
    db.commit()
    return doc_id

def run_validation():
    print("Setting up mock database for Risk Engine...")
    db = Session()
    try:
        client_id = uuid.uuid4()
        client = Client(id=client_id, name="Test Client")
        db.add(client)
        
        # Scenarios
        doc1 = create_scenario(db, client_id, "Partnership", "Positive", None)
        doc2 = create_scenario(db, client_id, "Customer Complaints", "Negative", None)
        doc3 = create_scenario(db, client_id, "Layoffs", "Negative", "HIGH")
        doc4 = create_scenario(db, client_id, "Regulatory Action", "Negative", "CRITICAL")
        
        engine = RiskEngine()
        
        print("Running Risk Engine Inference...")
        start_time = time.time()
        
        # Test latency and correctness
        engine.calculate_document_risk(db, doc1)
        engine.calculate_document_risk(db, doc2)
        engine.calculate_document_risk(db, doc3)
        engine.calculate_document_risk(db, doc4)
        
        # Throughput test
        for _ in range(96): # Total 100 iterations
            engine.calculate_document_risk(db, doc1)
            
        exec_time = time.time() - start_time
        avg_time = exec_time / 100.0
        throughput = 100.0 / exec_time if exec_time > 0 else 0
        
        print("\n--- PHASE 2.1 VALIDATION REPORT ---")
        
        # Check correctness
        correct = 0
        r1 = db.query(RiskEvent).filter(RiskEvent.document_id == doc1).first()
        r2 = db.query(RiskEvent).filter(RiskEvent.document_id == doc2).first()
        r3 = db.query(RiskEvent).filter(RiskEvent.document_id == doc3).first()
        r4 = db.query(RiskEvent).filter(RiskEvent.document_id == doc4).first()
        
        if r1 and r1.risk_level == "LOW": correct += 25; print(f"1. Positive Partnership -> Expected: LOW | Actual: {r1.risk_level} (Score: {r1.risk_score:.1f}) [PASS]")
        else: print("1. Positive Partnership [FAIL]")
            
        if r2 and r2.risk_level == "MEDIUM": correct += 25; print(f"2. Negative Customer Complaint -> Expected: MEDIUM | Actual: {r2.risk_level} (Score: {r2.risk_score:.1f}) [PASS]")
        else: print(f"2. Negative Customer Complaint [FAIL] Actual: {r2.risk_level if r2 else 'None'}")
            
        if r3 and r3.risk_level == "HIGH": correct += 25; print(f"3. Negative Layoff + High Trend -> Expected: HIGH | Actual: {r3.risk_level} (Score: {r3.risk_score:.1f}) [PASS]")
        else: print(f"3. Negative Layoff + High Trend [FAIL] Actual: {r3.risk_level if r3 else 'None'} Score: {r3.risk_score if r3 else 0}")
            
        if r4 and r4.risk_level == "CRITICAL": correct += 25; print(f"4. Negative Regulatory + Critical Trend -> Expected: CRITICAL | Actual: {r4.risk_level} (Score: {r4.risk_score:.1f}) [PASS]")
        else: print(f"4. Negative Regulatory + Critical Trend [FAIL] Actual: {r4.risk_level if r4 else 'None'} Score: {r4.risk_score if r4 else 0}")
        
        print(f"Classification Accuracy: {correct}%")
        print(f"Performance Metric: {avg_time:.4f}s avg per document ({throughput:.1f} docs/sec throughput per worker)")
        
        if correct == 100:
            print("Status: PASS")
        else:
            print("Status: FAIL")
            
    finally:
        db.close()

if __name__ == "__main__":
    run_validation()
