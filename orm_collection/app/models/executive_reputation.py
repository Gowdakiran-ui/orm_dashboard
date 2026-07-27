import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.db import Base

class ExecutiveReputationScore(Base):
    __tablename__ = "executive_reputation_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    
    executive_name = Column(String(255), nullable=False)
    score = Column(Float, nullable=False)
    grade = Column(String(2), nullable=False) # A+, A, B, C, D, F
    
    sentiment_component = Column(Float, nullable=False, default=0.0)
    risk_component = Column(Float, nullable=False, default=0.0)
    narrative_component = Column(Float, nullable=False, default=0.0)
    trend_component = Column(Float, nullable=False, default=0.0)
    visibility_component = Column(Float, nullable=False, default=0.0)
    
    confidence_score = Column(Float, nullable=False, default=1.0)
    reputation_trend = Column(String(20), nullable=False) # IMPROVING, STABLE, DECLINING
    
    top_positive_narrative = Column(String(255), nullable=True)
    top_negative_narrative = Column(String(255), nullable=True)
    
    # Observability columns
    run_id = Column(String(100))
    batch_id = Column(String(100))
    worker_id = Column(String(100))
    latency_ms = Column(Float)
    retry_count = Column(Integer)
    
    # Accuracy & Explainability columns (Phase 8.2)
    evidence_metadata = Column(JSONB)
    calculation_lineage = Column(JSONB)
    health_status = Column(String(50))
    data_coverage = Column(Float, default=0.40)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
