import uuid
from sqlalchemy import Column, String, DateTime, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    industry = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Narrative State Machine Observability
    narrative_processing_status = Column(String(50), default="NARRATIVE_PENDING")
    narrative_failure_reason = Column(String(4000))
    narrative_retry_count = Column(Integer, default=0)
    narrative_run_id = Column(String(100))
    narrative_batch_id = Column(String(100))
    narrative_latency_ms = Column(Float)
    narrative_failed_at = Column(DateTime(timezone=True))

    # Reputation State Machine Observability (Phase 8.1)
    reputation_processing_status = Column(String(50), default="REPUTATION_PENDING")
    reputation_failure_reason = Column(String(4000))
    reputation_retry_count = Column(Integer, default=0)
    reputation_run_id = Column(String(100))
    reputation_batch_id = Column(String(100))
    reputation_latency_ms = Column(Float)
    reputation_failed_at = Column(DateTime(timezone=True))

    # Executive Reputation State Machine Observability (Phase 9.1)
    exec_reputation_processing_status = Column(String(50), default="EXEC_REPUTATION_PENDING")
    exec_reputation_failure_reason = Column(String(4000))
    exec_reputation_retry_count = Column(Integer, default=0)
    exec_reputation_run_id = Column(String(100))
    exec_reputation_batch_id = Column(String(100))
    exec_reputation_latency_ms = Column(Float)
    exec_reputation_failed_at = Column(DateTime(timezone=True))

    # Benchmark State Machine Observability (Phase 10.1)
    benchmark_processing_status = Column(String(50), default="BENCHMARK_PENDING")
    benchmark_failure_reason = Column(String(4000))
    benchmark_retry_count = Column(Integer, default=0)
    benchmark_run_id = Column(String(100))
    benchmark_batch_id = Column(String(100))
    benchmark_latency_ms = Column(Float)
    benchmark_failed_at = Column(DateTime(timezone=True))
