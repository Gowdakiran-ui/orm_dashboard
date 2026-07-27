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

def run_validation():
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
        
        print("\n--- PHASE 2.3 VALIDATION REPORT ---")
        
        correct = 0
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

        if has_layoff: correct += 16; print("1. Layoff Narrative Detection [PASS]")
        else: print("1. Layoff Narrative Detection [FAIL]")
        
        if has_cust: correct += 16; print("2. Customer Complaint Narrative Detection [PASS]")
        else: print("2. Customer Complaint Narrative Detection [FAIL]")
        
        if has_cyber: correct += 16; print("3. Cybersecurity Narrative Detection [PASS]")
        else: print("3. Cybersecurity Narrative Detection [FAIL]")
        
        if has_reg: correct += 16; print("4. Regulatory Narrative Detection [PASS]")
        else: print("4. Regulatory Narrative Detection [FAIL]")
        
        if status_pass: correct += 16; print("5. Narrative Status Calculation [PASS]")
        else: print("5. Narrative Status Calculation [FAIL]")
        
        if agg_pass: correct += 20; print("6. Narrative Aggregation Accuracy [PASS]")
        else: print("6. Narrative Aggregation Accuracy [FAIL]")

        print(f"Classification Accuracy: {correct}%")
        print(f"Performance Metric: {avg_time:.4f}s avg per client ({throughput:.1f} clients/sec throughput per worker)")
        
        if correct == 100:
            print("Status: PASS")
        else:
            print("Status: FAIL")
            
    finally:
        db.close()

if __name__ == "__main__":
    run_validation()
