import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base


class DocumentFeedHit(Base):
    """
    Which seeded executive's search returned a document (the backfill's or the Run Pipeline's "Name" "Company" query), including a
    document that was already held. See database/migrations/0017_add_document_feed_hits.sql and services/seeding/attribution.py.
    A hit alone counts for nothing: the document is attributed to the executive only when its stored text also holds the company,
    the surname or a role word. Nothing else reads this table.
    """
    __tablename__ = "document_feed_hits"
    __table_args__ = (
        UniqueConstraint("document_id", "entity_id", name="uq_document_feed_hits_document_entity"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(30), nullable=False)
    query = Column(Text)
    seen_at = Column(DateTime(timezone=True), server_default=func.now())
