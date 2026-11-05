import uuid
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.db import Base


class SeededEntity(Base):
    """
    One row per executive / competitor proposed for a client by the seeding step (services/seeding).
    See database/migrations/0016_add_seeded_entities.sql.

    kind: "executive" | "competitor". rank: 1-based order (executives in role order, competitors in seed order).
    status: "active" (validated, entity created, shown first on its page), "needs_review" (failed validation, no
    entity, never shown), "retired" (removed by an operator; the entity row is left in place).
    entity_id is NULL while status is needs_review. Nothing else reads this table except the seeding service, the
    two engines' seeded-gate lookups and the two page endpoints.
    """
    __tablename__ = "seeded_entities"
    __table_args__ = (
        UniqueConstraint("client_id", "kind", "name", name="uq_seeded_entities_client_kind_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    rank = Column(Integer, nullable=False)
    role = Column(Text)
    context_term = Column(String(120))
    aliases = Column(JSONB)
    sources = Column(JSONB)
    pair_count_24m = Column(Integer)
    validated = Column(Boolean, nullable=False, default=False, server_default="false")
    status = Column(String(20), nullable=False, default="needs_review", server_default="needs_review")
    seeded_at = Column(DateTime(timezone=True), server_default=func.now())
