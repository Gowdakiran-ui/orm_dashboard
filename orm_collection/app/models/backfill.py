import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base


class BackfillSlice(Base):
    """
    One row per (client, source, query, date slice) of the one-time historical
    backfill. Lets a crashed or re-run backfill resume and never refetch a
    finished slice. See database/migrations/0014_add_backfill_slices.sql.

    status: PENDING (planned / failed-and-retryable), DONE, SPLIT (hit the
    per-call cap, replaced by smaller child slices), ERROR (retries exhausted),
    SKIPPED (deliberately not fetched; never picked up, never deleted).
    """
    __tablename__ = "backfill_slices"
    __table_args__ = (
        UniqueConstraint("client_id", "source", "query", "slice_start", "slice_end", name="uq_backfill_slices_slice"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    entity_name = Column(String(255), nullable=False)
    source = Column(String(30), nullable=False)
    query = Column(Text, nullable=False)
    slice_start = Column(DateTime(timezone=True), nullable=False)
    slice_end = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    item_count = Column(Integer)
    new_count = Column(Integer)
    error = Column(Text)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
