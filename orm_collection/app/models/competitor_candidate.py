import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.db import Base

class CompetitorCandidate(Base):
    __tablename__ = "competitor_candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    organization_name = Column(String(255), nullable=False, index=True)
    mention_count = Column(Integer, default=1, nullable=False)
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    source_documents = Column(JSONB, default=list)
    
    # Promotion tracking
    promoted_to_competitor_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    promoted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Phase 6 item 32: DB has these NOT NULL with a default; model was
    # looser (nullable defaults to True when omitted). Matching the DB,
    # which is already correctly enforcing this.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship to the promoted competitor entity
    promoted_competitor = relationship("Entity", foreign_keys=[promoted_to_competitor_id])
