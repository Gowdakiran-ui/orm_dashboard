import uuid
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class RSSFeed(Base):
    __tablename__ = "rss_feeds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feed_name = Column(String(255), nullable=False)
    feed_url = Column(String(1024), nullable=False, unique=True)
    category = Column(String(50)) # News, Business, Technology, Cybersecurity, Government, Press Release
    poll_interval_minutes = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    last_polled_at = Column(DateTime(timezone=True))
    
    # Position tracking
    last_entry_guid = Column(String(512))
    last_entry_published_at = Column(DateTime(timezone=True))
    
    # Reliability metadata
    reliability_score = Column(Float, default=1.0)
    
    # Configuration
    extract_full_article = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
