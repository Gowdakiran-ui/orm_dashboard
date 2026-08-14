import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.db import Base

class Narrative(Base):
    __tablename__ = "narratives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    narrative_name = Column(String(255), nullable=False)
    narrative_type = Column(String(100), nullable=False)
    
    mention_count = Column(Integer, nullable=False, default=0)
    sentiment_score = Column(Float, nullable=False, default=0.0)
    risk_score = Column(Float, nullable=False, default=0.0)
    trend_strength = Column(Float, nullable=False, default=0.0)
    
    status = Column(String(50), nullable=False) # EMERGING, GROWING, PEAK, DECLINING
    
    # Accuracy & Explainability
    summary_text = Column(String(4000), nullable=True)
    confidence_score = Column(Float, nullable=False, default=1.0)
    # Phase 6 item 30: DB column is `jsonb`, matching JSONB here.
    evidence_metadata = Column(JSONB, nullable=True)
    
    # Observability Metadata
    run_id = Column(String(100), nullable=True)
    batch_id = Column(String(100), nullable=True)
    worker_id = Column(String(100), nullable=True)
    latency_ms = Column(Float, nullable=True)
    retry_count = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
