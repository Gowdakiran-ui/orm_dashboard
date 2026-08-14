import uuid
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Boolean, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=True, index=True)
    
    alert_type = Column(String(50), nullable=False) # Risk, Trend, Sentiment, Executive
    severity = Column(String(20), nullable=False) # INFO, WARNING, HIGH, CRITICAL
    
    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    
    trigger_value = Column(Float, nullable=True)
    baseline_value = Column(Float, nullable=True)
    
    is_acknowledged = Column(Boolean, default=False, nullable=False)
    
    # Phase 6.1 Reliability and Observability Hardening (R2, R8)
    processing_status = Column(String(30), nullable=False, default="ALERT_PENDING")
    run_id = Column(String(64), nullable=True)
    batch_id = Column(String(64), nullable=True)
    worker_id = Column(String(64), nullable=True)
    latency_ms = Column(Float, nullable=True)
    retry_count = Column(Integer, nullable=True, default=0)
    # Phase 6 item 31: DB column is `text` (unbounded); String (no length
    # here, but still a VARCHAR-family type) was a formal type mismatch.
    failure_reason = Column(Text, nullable=True)

    # Phase 6 item 29: DB columns are native Postgres `json`. Previously
    # JSONEncodedDict (impl=TEXT) -- worked at the Python level since the
    # custom type round-trips dict/list either way, but the DB<->model type
    # declaration mismatch meant a future `alembic revision --autogenerate`
    # could try to narrow these back to text. Using the generic SQLAlchemy
    # JSON type instead, which matches the live `json` (not `jsonb`) type.
    state_history = Column(JSON, nullable=True)

    # Phase 6.2 Accuracy Hardening Columns
    confidence_score = Column(Float, nullable=True)
    evidence_score = Column(Float, nullable=True)
    article_count = Column(Integer, nullable=True, default=1)
    supporting_signals = Column(JSON, nullable=True)
    explainability = Column(JSON, nullable=True)
    lifecycle_status = Column(String(30), nullable=False, default="NEW")
    lifecycle_history = Column(JSON, nullable=True)
    escalation_history = Column(JSON, nullable=True)
    human_summary = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

