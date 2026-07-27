"""
AlertClientState — Phase 6.1 State Machine

Tracks per-client Alert Engine processing state across Celery runs.
This provides deterministic state transitions, retry visibility, and
run correlation. One row per client (upserted on each run).
"""
import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base


class AlertClientState(Base):
    """
    State machine for alert generation per client.

    Valid states:
        ALERT_PENDING    → Initial state; no run has been executed yet.
        ALERT_PROCESSING → A run is currently in progress.
        ALERT_COMPLETE   → Last run completed successfully.
        ALERT_FAILED     → Last run failed and no retry is scheduled.
        ALERT_RETRYING   → Failed but a retry is queued with exponential backoff.
        ALERT_SKIPPED    → Client was skipped (no entities or events).

    Valid transitions:
        ALERT_PENDING    → ALERT_PROCESSING
        ALERT_PROCESSING → ALERT_COMPLETE
        ALERT_PROCESSING → ALERT_FAILED
        ALERT_PROCESSING → ALERT_RETRYING
        ALERT_PROCESSING → ALERT_SKIPPED
        ALERT_FAILED     → ALERT_RETRYING
        ALERT_FAILED     → ALERT_PROCESSING
        ALERT_RETRYING   → ALERT_PROCESSING
        ALERT_COMPLETE   → ALERT_PROCESSING  (next scheduled run)
        ALERT_SKIPPED    → ALERT_PROCESSING
    """
    __tablename__ = "alert_client_states"

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
        default="ALERT_PENDING"
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
