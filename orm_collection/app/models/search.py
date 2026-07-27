import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class SearchSourceConfiguration(Base):
    __tablename__ = "search_source_configurations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String(50), nullable=False, unique=True) # e.g. 'reddit', 'youtube'
    enabled = Column(Boolean, default=True)
    daily_quota = Column(Integer, default=10000)
    rate_limit = Column(Integer, default=60) # requests per minute
    reliability_score = Column(Float, default=1.0)
    source_priority = Column(Integer, default=1)

class SearchCursor(Base):
    __tablename__ = "search_cursors"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keyword_id = Column(UUID(as_uuid=True), ForeignKey("entity_keywords.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(50), nullable=False)
    cursor_value = Column(String(512)) # last_post_id or nextPageToken
    last_searched_at = Column(DateTime(timezone=True))

class SearchJob(Base):
    __tablename__ = "search_jobs"
    
    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String(50), nullable=False)
    keyword = Column(String(255), nullable=False)
    status = Column(String(50), default="pending") # pending, processing, completed, failed
    
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    
    results_found = Column(Integer, default=0)
    results_saved = Column(Integer, default=0)
    results_matched = Column(Integer, default=0)
