import uuid
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func
from app.core.db import Base


class PipelineRunCost(Base):
    """What one Run Pipeline cost, per run and client: Apify usage (Reddit reports it; Instagram is estimated from the result count),
    LLM calls and tokens with an estimated dollar cost, and keyword search calls. One row per run. See
    database/migrations/0020_add_pipeline_run_costs.sql and services/pipeline_cost.py. Written best-effort; read only by the
    super-admin diagnostics endpoint. No score reads it."""
    __tablename__ = "pipeline_run_costs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(String(64), nullable=False, unique=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    apify_calls = Column(Integer, nullable=False, default=0)
    apify_cost_usd = Column(Float, nullable=False, default=0.0)
    apify_cost_estimated = Column(Boolean, nullable=False, default=False)
    apify_by_source = Column(JSONB)
    llm_calls = Column(Integer, nullable=False, default=0)
    llm_tokens_prompt = Column(BigInteger, nullable=False, default=0)
    llm_tokens_completion = Column(BigInteger, nullable=False, default=0)
    llm_est_cost_usd = Column(Float, nullable=False, default=0.0)
    llm_by_type = Column(JSONB)
    search_calls = Column(Integer, nullable=False, default=0)
    search_by_source = Column(JSONB)
    finalized = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
