import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.db import Base
import json

# Fallback for SQLite which doesn't support JSONB
from sqlalchemy.types import TypeDecorator, TEXT

class JSONEncodedDict(TypeDecorator):
    impl = TEXT
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return value
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if isinstance(value, str):
                return json.loads(value)
            return value
        return value

class RiskEvent(Base):
    __tablename__ = "risk_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=True, index=True)
    
    risk_score = Column(Float, nullable=False, default=0.0) # 0-100
    risk_level = Column(String(20), nullable=False) # LOW, MEDIUM, HIGH, CRITICAL
    confidence_score = Column(Float, nullable=False, default=1.0)
    
    # Store list of risk factors [{"type": "Topic", "factor": "Layoffs", "weight": 40}, ...]
    # Using JSONEncodedDict for SQLite compatibility in tests, normally we'd use JSONB for Postgres
    risk_factors = Column(JSONEncodedDict, nullable=True) 

    # Phase 5.1 Observability & Metadata (R8)
    run_id = Column(String(64), nullable=True)
    batch_id = Column(String(64), nullable=True)
    worker_id = Column(String(64), nullable=True)
    latency_ms = Column(Float, nullable=True)
    retry_count = Column(Integer, nullable=True, default=0)
    
    # Phase 5.2 Accuracy & Explainability
    source_reliability = Column(Float, nullable=True)
    # Phase 6 item 29: DB column is native Postgres `json` (unlike
    # risk_factors above, which is genuinely `text` and correctly stays
    # JSONEncodedDict). Using the generic SQLAlchemy JSON type to match.
    explainability = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
