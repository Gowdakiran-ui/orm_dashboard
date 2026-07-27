import uuid
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class DocumentSentiment(Base):
    __tablename__ = "document_sentiments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    sentiment_label = Column(String(50), nullable=False) # Positive, Neutral, Negative
    sentiment_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    source_reliability = Column(Float, default=1.0)
    weighted_sentiment_score = Column(Float, nullable=False)
    explainability_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("document_id", name="uq_document_sentiments_document_id"),
    )

class EntitySentiment(Base):
    __tablename__ = "entity_sentiments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    sentiment_label = Column(String(50), nullable=False)
    sentiment_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    explainability_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("document_id", "entity_id", name="uq_entity_sentiments_doc_entity"),
    )
