import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class ClientProcessingSummary(Base):
    __tablename__ = "client_processing_summary"

    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)
    client_name = Column(String(255), nullable=False)
    documents_collected = Column(Integer, default=0)
    documents_processed = Column(Integer, default=0)
    entity_matches = Column(Integer, default=0)
    topics_generated = Column(Integer, default=0)
    sentiments_generated = Column(Integer, default=0)
    risks_generated = Column(Integer, default=0)
    alerts_generated = Column(Integer, default=0)
    narratives_generated = Column(Integer, default=0)
    reputation_score = Column(Float, default=0.0)
    last_processed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
