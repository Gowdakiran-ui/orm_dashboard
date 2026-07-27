"""
RiskClientState — Phase 5.1 State Machine

Tracks per-client Risk Engine processing state across Celery runs.
This provides deterministic state transitions, retry visibility, and
run correlation. One row per client (upserted on each run).
"""
import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base


class RiskClientState(Base):
    """
    State machine for risk calculation per client.

    Valid states:
        RISK_PENDING    → Initial state; no run has been executed yet.
        RISK_PROCESSING → A run is currently in progress.
        RISK_COMPLETE   → Last run completed successfully.
        RISK_FAILED     → Last run failed and no retry is scheduled.
        RISK_RETRYING   → Failed but a retry is queued with exponential backoff.
        RISK_SKIPPED    → Client was skipped (no entities, no documents).

    Valid transitions:
        RISK_PENDING    → RISK_PROCESSING
        RISK_PROCESSING → RISK_COMPLETE
        RISK_PROCESSING → RISK_FAILED
        RISK_PROCESSING → RISK_RETRYING
        RISK_FAILED     → RISK_RETRYING
        RISK_RETRYING   → RISK_PROCESSING
        RISK_COMPLETE   → RISK_PROCESSING  (next scheduled run)
        RISK_PROCESSING → RISK_SKIPPED
    """
    __tablename__ = "risk_client_states"

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
        default="RISK_PENDING"
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
