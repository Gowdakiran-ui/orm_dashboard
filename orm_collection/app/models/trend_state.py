"""
TrendClientState — Phase 4.1 State Machine

Tracks per-client trend detection processing state across Celery runs.
This provides deterministic state transitions, retry visibility, and
run correlation. One row per client (upserted on each run).
"""
import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base


class TrendClientState(Base):
    """
    State machine for trend detection per client.

    Valid states:
        TREND_PENDING    → Initial state; no run has been executed yet.
        TREND_PROCESSING → A run is currently in progress.
        TREND_COMPLETE   → Last run completed successfully.
        TREND_FAILED     → Last run failed and no retry is scheduled.
        TREND_RETRYING   → Failed but a retry is queued with exponential backoff.
        TREND_SKIPPED    → Client was skipped (no entities, no documents).

    Valid transitions:
        TREND_PENDING    → TREND_PROCESSING
        TREND_PROCESSING → TREND_COMPLETE
        TREND_PROCESSING → TREND_FAILED
        TREND_PROCESSING → TREND_RETRYING
        TREND_FAILED     → TREND_RETRYING
        TREND_RETRYING   → TREND_PROCESSING
        TREND_COMPLETE   → TREND_PROCESSING  (next scheduled run)
        TREND_PROCESSING → TREND_SKIPPED

    Invalid transitions (enforced at application level):
        TREND_COMPLETE  → TREND_FAILED     (requires TREND_PROCESSING intermediate)
        TREND_PENDING   → TREND_COMPLETE   (must pass through PROCESSING)
        TREND_FAILED    → TREND_COMPLETE   (must pass through RETRYING → PROCESSING)
    """
    __tablename__ = "trend_client_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK to clients — one state row per client
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    # Current processing state
    processing_status = Column(
        String(30),
        nullable=False,
        default="TREND_PENDING"
    )

    # Correlation IDs for the last run
    run_id = Column(String(64), nullable=True)
    batch_id = Column(String(64), nullable=True)

    # Retry tracking
    retry_count = Column(Integer, nullable=False, default=0)
    last_retry_at = Column(DateTime(timezone=True), nullable=True)

    # Execution timestamps
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)

    # Error tracking
    last_error = Column(Text, nullable=True)

    # Row lifecycle
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
