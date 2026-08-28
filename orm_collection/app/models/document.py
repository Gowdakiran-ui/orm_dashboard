import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Float, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(Text, unique=True, nullable=False)
    content_hash = Column(String(64), unique=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), index=True)
    document_type = Column(String(50)) # 'article', 'post', 'video', 'review'
    title = Column(Text)
    normalized_content = Column(Text, nullable=False)
    author = Column(String(255))
    published_at = Column(DateTime(timezone=True))
    collected_at = Column(DateTime(timezone=True), server_default=func.now())
    language = Column(String(10), default="en")
    raw_storage_path = Column(String(1024))

    # Processing State Machine — Phase C
    processing_status = Column(String(20), default="PENDING")
    # Valid states: PENDING | PROCESSING | MATCHED | FAILED | SKIPPED | RETRYING
    processing_started_at = Column(DateTime(timezone=True))  # set when processing_status -> PROCESSING; staleness clock for document_processing_watchdog

    # Reliability Metadata — Phases D, E, F
    match_retry_count = Column(Integer, default=0)        # Retry attempt counter
    match_failed_at = Column(DateTime(timezone=True))     # Timestamp of terminal failure
    match_failure_reason = Column(Text)                   # Last failure message (truncated)
    match_run_id = Column(String(64))                     # Correlation: run UUID
    match_batch_id = Column(String(64))                   # Correlation: batch UUID
    match_processing_time_ms = Column(Float)              # Execution time in milliseconds

    # Topic Classification Reliability — Phase 2.1 Hardening
    topic_processing_status = Column(String(30), default="PENDING")
    topic_retry_count = Column(Integer, default=0)
    topic_failed_at = Column(DateTime(timezone=True))
    topic_failure_reason = Column(Text)
    topic_run_id = Column(String(64))
    topic_batch_id = Column(String(64))
    topic_processing_time_ms = Column(Float)

    # Sentiment Analysis Reliability — Phase 3.1 Hardening
    sentiment_processing_status = Column(String(30), default="SENTIMENT_PENDING")
    sentiment_retry_count = Column(Integer, default=0)
    sentiment_failed_at = Column(DateTime(timezone=True))
    sentiment_failure_reason = Column(Text)
    sentiment_run_id = Column(String(64))
    sentiment_batch_id = Column(String(64))
    sentiment_processing_time_ms = Column(Float)

    matches = relationship("DocumentMatch", back_populates="document", cascade="all, delete-orphan")

class DocumentMatch(Base):
    __tablename__ = "document_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    matched_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword_id = Column(UUID(as_uuid=True), ForeignKey("entity_keywords.id"), index=True)
    matched_text = Column(Text)
    match_type = Column(String(50))
    match_confidence = Column(Float, default=1.0)
    # Phase 6 item 30: DB column is `jsonb`. Using JSONB (not generic JSON)
    # matches live data and makes jsonb operators/indexes reachable through
    # the ORM.
    match_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", back_populates="matches")
