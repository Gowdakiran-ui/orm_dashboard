import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class CollectionJob(Base):
    __tablename__ = "collection_jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("rss_feeds.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="pending") # pending, processing, completed, failed
    
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    
    documents_found = Column(Integer, default=0)
    documents_saved = Column(Integer, default=0)
    documents_matched = Column(Integer, default=0)
    documents_deduplicated = Column(Integer, default=0)
    documents_failed = Column(Integer, default=0)
