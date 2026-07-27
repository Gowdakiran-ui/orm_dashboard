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
from app.models.trends import TrendEvent
from app.services.intelligence.trend_detector import TrendDetector

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

@compiles(PG_UUID, 'sqlite')
def compile_uuid(element, compiler, **kw):
    return "CHAR(32)"

# Create an in-memory SQLite database for fast testing
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
Session = sessionmaker(bind=engine)

def setup_mock_data(db):
    client_id = uuid.uuid4()
    client = Client(id=client_id, name="Test Client")
    db.add(client)
    
    entity_id = uuid.uuid4()
    entity = Entity(id=entity_id, client_id=client_id, name="Test Entity")
    db.add(entity)
    
    topic_id = uuid.uuid4()
    topic = Topic(id=topic_id, name="Test Topic", is_active=True)
    db.add(topic)
    db.commit()

    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Generate 7 days of baseline data (1 doc per day = 7 baseline docs)
    # Baseline total: 7 docs. Avg per day: 1.0
    for i in range(1, 8):
        doc_time = now - datetime.timedelta(days=i, hours=12)
        doc = Document(id=uuid.uuid4(), url=f"http://test.com/base{i}", normalized_content="base", collected_at=doc_time)
        db.add(doc)
        db.commit()
        
        # Mention
        db.add(EntityMention(document_id=doc.id, entity_id=entity_id, mention_count=1))
        # Topic
        db.add(DocumentTopic(document_id=doc.id, topic_id=topic_id, confidence_score=0.9))
        # Sentiment (Negative to test sentiment spikes)
        db.add(DocumentSentiment(document_id=doc.id, sentiment_label="Negative", sentiment_score=-1.0, confidence_score=0.9, weighted_sentiment_score=-1.0))
    
    # Generate last 24h data (Spike: 10 docs today)
    # Current total: 10 docs.
    for i in range(10):
        doc_time = now - datetime.timedelta(hours=i+1)
        doc = Document(id=uuid.uuid4(), url=f"http://test.com/spike{i}", normalized_content="spike", collected_at=doc_time)
        db.add(doc)
        db.commit()
        
        # Mention
        db.add(EntityMention(document_id=doc.id, entity_id=entity_id, mention_count=1))
        # Topic
        db.add(DocumentTopic(document_id=doc.id, topic_id=topic_id, confidence_score=0.9))
        # Sentiment
        db.add(DocumentSentiment(document_id=doc.id, sentiment_label="Negative", sentiment_score=-1.0, confidence_score=0.9, weighted_sentiment_score=-1.0))
        
    db.commit()
    return client_id

def run_validation():
    print("Setting up mock database for Trend Detection...")
    db = Session()
    try:
        client_id = setup_mock_data(db)
        detector = TrendDetector()
        
        print("Running Trend Detection...")
        start_time = time.time()
        
        # Test 100 iterations for throughput testing
        for _ in range(100):
            detector.detect_trends(db, client_id)
            
        exec_time = time.time() - start_time
        avg_time = exec_time / 100.0
        throughput = 100.0 / exec_time if exec_time > 0 else 0
        
        # Check generated events
        events = db.query(TrendEvent).filter(TrendEvent.client_id == client_id).all()
        # Since we ran it 100 times, and it creates 3 events per run, we should have 300 events
        
        # Analyze the latest events for accuracy
        mention_events = [e for e in events if e.trend_type == "Mention"]
        topic_events = [e for e in events if e.trend_type == "Topic"]
        sentiment_events = [e for e in events if e.trend_type == "Sentiment"]
        
        print("\n--- PHASE 1E VALIDATION REPORT ---")
        
        # Baseline avg should be 1.0, current should be 10.0 -> Percentage change = (10 - 1) / 1 * 100 = 900%
        # Severity should be CRITICAL (>= 500%)
        accuracy = 0
        if mention_events and mention_events[0].percentage_change == 900.0 and mention_events[0].severity == "CRITICAL":
            accuracy += 33.3
        if topic_events and topic_events[0].percentage_change == 900.0 and topic_events[0].severity == "CRITICAL":
            accuracy += 33.3
        if sentiment_events and sentiment_events[0].percentage_change == 900.0 and sentiment_events[0].severity == "CRITICAL":
            accuracy += 33.4
            
        print(f"Mention Spike Detection: {'PASS' if mention_events else 'FAIL'} (Expected +900%)")
        print(f"Topic Spike Detection: {'PASS' if topic_events else 'FAIL'} (Expected +900%)")
        print(f"Sentiment Spike Detection: {'PASS' if sentiment_events else 'FAIL'} (Expected +900%)")
        
        print(f"Trend Calculation Accuracy: {accuracy:.1f}%")
        print(f"Performance Metric: {avg_time:.4f}s avg per client ({throughput:.1f} clients/sec throughput per worker)")
        
        if accuracy >= 99.0:
            print("Status: PASS")
        else:
            print("Status: FAIL (Logic error in trend calculation)")
            
    finally:
        db.close()

if __name__ == "__main__":
    run_validation()
