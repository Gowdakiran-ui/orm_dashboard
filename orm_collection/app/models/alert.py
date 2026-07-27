import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Boolean, Integer
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
    failure_reason = Column(String, nullable=True)
    
    from app.models.risk import JSONEncodedDict
    state_history = Column(JSONEncodedDict, nullable=True)
    
    # Phase 6.2 Accuracy Hardening Columns
    confidence_score = Column(Float, nullable=True)
    evidence_score = Column(Float, nullable=True)
    article_count = Column(Integer, nullable=True, default=1)
    supporting_signals = Column(JSONEncodedDict, nullable=True)
    explainability = Column(JSONEncodedDict, nullable=True)
    lifecycle_status = Column(String(30), nullable=False, default="NEW")
    lifecycle_history = Column(JSONEncodedDict, nullable=True)
    escalation_history = Column(JSONEncodedDict, nullable=True)
    human_summary = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

