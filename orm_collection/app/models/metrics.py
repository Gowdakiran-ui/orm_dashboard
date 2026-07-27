import uuid
from sqlalchemy import Column, Integer, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class MatchingMetrics(Base):
    __tablename__ = "matching_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    documents_processed = Column(Integer, default=0)
    matches_found = Column(Integer, default=0)
    processing_time = Column(Float, default=0.0) # in seconds or milliseconds
    keywords_loaded = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
