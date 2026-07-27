import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.db import Base

class CompetitorBenchmark(Base):
    __tablename__ = "competitor_benchmarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    competitor_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    
    reputation_score = Column(Float, nullable=False, default=0.0)
    executive_reputation_score = Column(Float, nullable=False, default=0.0)
    sentiment_score = Column(Float, nullable=False, default=0.0)
    risk_score = Column(Float, nullable=False, default=0.0)
    visibility_score = Column(Float, nullable=False, default=0.0)
    share_of_voice = Column(Float, nullable=False, default=0.0)
    
    top_narrative = Column(String(255), nullable=True)
    rank = Column(Integer, nullable=False, default=0)
    
    # Observability columns
    run_id = Column(String(100))
    batch_id = Column(String(100))
    worker_id = Column(String(100))
    latency_ms = Column(Float)
    retry_count = Column(Integer)
    
    # Accuracy & Explainability columns (Phase 10.2)
    calculation_lineage = Column(JSONB)
    evidence_metadata = Column(JSONB)
    health_status = Column(String(50))
    confidence_score = Column(Float)
    data_coverage = Column(Float, default=0.40)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
