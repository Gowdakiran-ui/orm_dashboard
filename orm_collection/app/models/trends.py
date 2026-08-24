"""
TrendEvent — Phase 4.1 Hardened

Changes from Phase 4.0 baseline:
  - Added run_id         : correlates event to a specific Celery task execution
  - Added batch_id       : correlates event to a specific client batch
  - Added trend_date     : DATE of the detection window (enables deduplication)
  - Added baseline_established : flags whether this is a cold-start event (False)
                                 or a normal trend event with an established baseline

The application-level upsert in TrendDetector ensures only one TrendEvent
exists per (client_id, trend_type, entity_id, topic_id, trend_date).
The database-level unique index enforces this at storage level using
COALESCE for nullable columns.
"""
import uuid
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Date, Boolean, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text
from app.core.db import Base


class TrendEvent(Base):
    __tablename__ = "trend_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Ownership
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Signal type: "Mention" | "Topic" | "Sentiment"
    trend_type = Column(String(50), nullable=False)

    # Signal source — nullable depending on trend_type
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    topic_id = Column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Detection values
    baseline_value = Column(Float, nullable=False, default=0.0)
    current_value = Column(Float, nullable=False, default=0.0)
    percentage_change = Column(Float, nullable=False, default=0.0)

    # Severity: LOW | MEDIUM | HIGH | CRITICAL
    severity = Column(String(20), nullable=False)

    # R4.1 Observability — run correlation
    run_id = Column(String(64), nullable=True)
    batch_id = Column(String(64), nullable=True)

    # R5 Duplicate protection — one event per (client, type, entity/topic) per day
    trend_date = Column(Date, nullable=True, index=True)

    # R9 Baseline Safety — False if this is a first-observation cold-start event
    baseline_established = Column(Boolean, nullable=False, default=True)

    # Phase 4.2 Explainability & Metadata
    trend_direction = Column(String(50), nullable=True)
    # Phase 6 item 31: DB column is `text` (unbounded). String (no length
    # here) is a VARCHAR-family type -- a formal type mismatch even though
    # it wasn't actively truncating anything.
    decision_reason = Column(Text, nullable=True)
    triggering_documents = Column(JSON, nullable=True)
    time_window = Column(String(50), nullable=True, default="24h_vs_7d")

    created_at = Column(DateTime(timezone=True), server_default=func.now())



# ---------------------------------------------------------------------------
# Phase 4.1 — Unique index for duplicate protection
#
# PostgreSQL treats NULL as distinct in standard unique constraints, so
# COALESCE is used to normalize nullable entity_id and topic_id to empty
# string sentinels for uniqueness evaluation.
#
# This is a functional index and is defined outside the model as a module-level
# DDL object. The Index below is a declarative placeholder only -- the real
# DDL (with the COALESCE expressions) lives in database/schema.sql, the
# project's source of truth for DB structure (see CLAUDE.md — Remove Alembic).
#
# Effective constraint:
#   UNIQUE (client_id, trend_type, COALESCE(entity_id::text,''),
#           COALESCE(topic_id::text,''), trend_date)
# ---------------------------------------------------------------------------
uq_trend_events_daily = Index(
    "uq_trend_events_daily",
    TrendEvent.client_id,
    TrendEvent.trend_type,
    TrendEvent.trend_date,
    # Functional expression columns are not directly supported in SQLAlchemy
    # ORM Index() for COALESCE. The actual DDL is in database/schema.sql's
    # uq_trend_events_daily definition.
    unique=False  # uniqueness enforced by schema.sql's functional index
)
