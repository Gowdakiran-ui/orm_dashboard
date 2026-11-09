import uuid
from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.db import Base


class AiCheckRun(Base):
    """One "What AI says about you" run for one client. See database/migrations/0018_add_ai_check.sql and
    services/ai_check/. Read only by the AI-check endpoints; no score or report reads it."""
    __tablename__ = "ai_check_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','stopped_at_cap','failed')", name="ai_check_runs_status_check"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="running")
    model = Column(String(100), nullable=False)
    web_results = Column(Integer, nullable=False)
    repeats = Column(Integer, nullable=False)
    prompt_count = Column(Integer, nullable=False)
    estimated_cost_usd = Column(Float)
    cost_usd = Column(Float, nullable=False, default=0.0)
    calls_ok = Column(Integer, nullable=False, default=0)
    calls_failed = Column(Integer, nullable=False, default=0)
    error = Column(Text)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))


class AiCheckAnswer(Base):
    """One stored answer: the prompt, the answer text, and the pages and domains it cited, tied to its run."""
    __tablename__ = "ai_check_answers"
    __table_args__ = (
        UniqueConstraint("run_id", "prompt_key", "repeat_index", name="uq_ai_check_answers_run_prompt_repeat"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("ai_check_runs.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    prompt_key = Column(String(40), nullable=False)
    prompt_text = Column(Text, nullable=False)
    repeat_index = Column(Integer, nullable=False)
    answer_text = Column(Text)
    cited_urls = Column(JSONB)
    cited_domains = Column(JSONB)
    cost_usd = Column(Float)
    tokens_prompt = Column(Integer)
    tokens_completion = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
