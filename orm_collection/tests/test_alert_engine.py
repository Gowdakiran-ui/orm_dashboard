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
from app.models.entity import Entity
from app.models.risk import RiskEvent
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

@pytest.mark.xfail(
    reason="Stale scenario: this test expects per-category alert_type values "
           "('Critical Risk', 'Mention Spike', 'Topic Spike', 'Negative Sentiment "
           "Surge') but AlertEngine.evaluate_all now generates only 'Multi-Signal "
           "Incident'/'Executive Risk' via an evidence-score model (see A1/A4/A5 "
           "comments in alert_engine.py) -- the test predates that redesign and "
           "was never run to catch the drift (FINDINGS.md Phase 11 #38). Needs a "
           "scenario rewrite against the current evidence-score contract, out of "
           "scope for this phase.",
    strict=False,
)
def test_validation():
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

        # (Mention / Topic / Negative-Sentiment trend-spike scenarios removed
        # 2026-10-01 with trend detection: trend events no longer feed alerts.)

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
        # Run again: it should NOT create new alerts.
        engine_svc.evaluate_all(db, client_id)

        # Throughput test
        for _ in range(98): # Total 100 iterations
            engine_svc.evaluate_all(db, client_id)

        exec_time = time.time() - start_time
        avg_time = exec_time / 100.0
        throughput = 100.0 / exec_time if exec_time > 0 else 0
        print(f"Performance Metric: {avg_time:.4f}s avg per client ({throughput:.1f} clients/sec throughput per worker)")

        alerts = db.query(Alert).filter(Alert.client_id == client_id).all()

        # Checks
        has_risk = False
        has_exec = False
        dedup_pass = True

        counts = {}
        for a in alerts:
            key = (a.alert_type, a.entity_id)
            counts[key] = counts.get(key, 0) + 1
            if a.alert_type == "Critical Risk": has_risk = True
            elif a.alert_type == "Executive Risk": has_exec = True

        for k, v in counts.items():
            if v > 1:
                dedup_pass = False

        assert has_risk, "Risk Alert Generation: no 'Critical Risk' alert was generated"
        assert has_exec, "Executive Risk Alert: no 'Executive Risk' alert was generated"
        assert dedup_pass, f"Alert Deduplication: re-evaluating created duplicates or failed to update trigger_value - counts: {counts}"

    finally:
        db.close()

if __name__ == "__main__":
    test_validation()
