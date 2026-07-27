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
from app.models.entity import Entity
from app.models.risk import RiskEvent
from app.models.trends import TrendEvent
from app.models.alert import Alert
from app.services.intelligence.alert_engine import AlertEngine

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

def run_validation():
    print("Setting up mock database for Alert Engine...")
    db = Session()
    try:
        client_id = uuid.uuid4()
        client = Client(id=client_id, name="Test Client")
        db.add(client)
        
        # 1. High Risk Alert setup
        ent1 = Entity(id=uuid.uuid4(), client_id=client_id, name="Standard Entity")
        db.add(ent1)
        r1 = RiskEvent(client_id=client_id, entity_id=ent1.id, risk_score=80.0, risk_level="CRITICAL", risk_factors=[])
        db.add(r1)

        # 2. Mention Spike
        ent2 = Entity(id=uuid.uuid4(), client_id=client_id, name="Mention Entity")
        db.add(ent2)
        t1 = TrendEvent(client_id=client_id, entity_id=ent2.id, trend_type="Mention", percentage_change=75.0, severity="HIGH")
        db.add(t1)

        # 3. Topic Spike
        t2 = TrendEvent(client_id=client_id, entity_id=None, trend_type="Topic", percentage_change=120.0, severity="CRITICAL")
        db.add(t2)

        # 4. Negative Sentiment Surge
        t3 = TrendEvent(client_id=client_id, entity_id=None, trend_type="Sentiment", percentage_change=60.0, severity="MEDIUM")
        db.add(t3)

        # 5. Executive Risk Alert
        ent_exec = Entity(id=uuid.uuid4(), client_id=client_id, name="CEO John Doe")
        db.add(ent_exec)
        r2 = RiskEvent(client_id=client_id, entity_id=ent_exec.id, risk_score=85.0, risk_level="CRITICAL", risk_factors=[{"type": "Sentiment", "factor": "Negative"}])
        db.add(r2)

        db.commit()

        engine_svc = AlertEngine()
        
        print("Running Alert Engine Inference...")
        start_time = time.time()
        
        # Test latency and correctness
        engine_svc.evaluate_all(db, client_id)
        
        # 6. Test Deduplication
        # Run again, it should NOT create new alerts, but might update trigger values. Let's create a new worse trend for mention
        t1_worse = TrendEvent(client_id=client_id, entity_id=ent2.id, trend_type="Mention", percentage_change=90.0, severity="CRITICAL")
        db.add(t1_worse)
        db.commit()
        
        engine_svc.evaluate_all(db, client_id)
        
        # Throughput test
        for _ in range(98): # Total 100 iterations
            engine_svc.evaluate_all(db, client_id)
            
        exec_time = time.time() - start_time
        avg_time = exec_time / 100.0
        throughput = 100.0 / exec_time if exec_time > 0 else 0
        
        print("\n--- PHASE 2.2 VALIDATION REPORT ---")
        
        correct = 0
        alerts = db.query(Alert).filter(Alert.client_id == client_id).all()
        
        # Checks
        has_risk = False
        has_mention = False
        has_topic = False
        has_sentiment = False
        has_exec = False
        dedup_pass = True
        
        counts = {}
        for a in alerts:
            key = (a.alert_type, a.entity_id)
            counts[key] = counts.get(key, 0) + 1
            if a.alert_type == "Critical Risk": has_risk = True
            elif a.alert_type == "Mention Spike":
                has_mention = True
                if a.trigger_value != 90.0: dedup_pass = False # Check if it updated
            elif a.alert_type == "Topic Spike": has_topic = True
            elif a.alert_type == "Negative Sentiment Surge": has_sentiment = True
            elif a.alert_type == "Executive Risk": has_exec = True

        for k, v in counts.items():
            if v > 1:
                dedup_pass = False
        
        if has_risk: correct += 16; print("1. Risk Alert Generation [PASS]")
        else: print("1. Risk Alert Generation [FAIL]")
        
        if has_mention: correct += 16; print("2. Mention Spike Alert [PASS]")
        else: print("2. Mention Spike Alert [FAIL]")
        
        if has_topic: correct += 16; print("3. Topic Spike Alert [PASS]")
        else: print("3. Topic Spike Alert [FAIL]")
        
        if has_sentiment: correct += 16; print("4. Negative Sentiment Surge Alert [PASS]")
        else: print("4. Negative Sentiment Surge Alert [FAIL]")
        
        if has_exec: correct += 16; print("5. Executive Risk Alert [PASS]")
        else: print("5. Executive Risk Alert [FAIL]")
        
        if dedup_pass: correct += 20; print("6. Alert Deduplication [PASS]")
        else: print("6. Alert Deduplication [FAIL] - Counts: " + str(counts))

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
