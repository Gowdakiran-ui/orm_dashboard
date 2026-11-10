import uuid
from sqlalchemy import Boolean, Column, String, Text, Integer, Float, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
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


class AiCheckFlag(Base):
    """The triage of one distinct sentence in an AI-check run's answers: is it a serious accusation about the client or an
    executive, and is it stated as fact. `flagged` = accusation about the client/executive stated as plain fact. `event` is the short
    English phrase used to find the matching XOOP incident. See database/migrations/0019_add_ai_check_flags.sql."""
    __tablename__ = "ai_check_flags"
    __table_args__ = (
        CheckConstraint("about IS NULL OR about IN ('client','executive','other')", name="ai_check_flags_about_check"),
        CheckConstraint("framing IS NULL OR framing IN ('FACT','ATTRIBUTED','HEDGED')", name="ai_check_flags_framing_check"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("ai_check_runs.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    sentence = Column(Text, nullable=False)
    occurrences = Column(JSONB)          # [{"prompt": key, "repeats": [1, 2]}]
    accusation = Column(Boolean, nullable=False)
    about = Column(String(20))
    framing = Column(String(12))
    flagged = Column(Boolean, nullable=False, default=False)
    event = Column(String(200))
    inline_domains = Column(JSONB)
    cited_domains = Column(JSONB)
    cost_usd = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Which XOOP incident the sentence was matched to (migration 0021): the incident's lead document, NULL = none. match_checked
    # is false until the one model call has been made and read.
    matched_document_id = Column(UUID(as_uuid=True))
    match_checked = Column(Boolean, nullable=False, default=False)
    match_cost_usd = Column(Float)
