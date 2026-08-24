import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.db import Base

class SourceCategory(Base):
    __tablename__ = "source_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    base_reliability_score = Column(Numeric(3, 2), default=1.00)

class Source(Base):
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = Column(UUID(as_uuid=True), ForeignKey("source_categories.id"), index=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False) # rss, reddit, etc.
    url = Column(String(1024), unique=True)
    schedule_cron = Column(String(50), nullable=False)
    query_template = Column(Text)
    is_active = Column(Boolean, default=True)

class SourceHealth(Base):
    __tablename__ = "source_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(String(50))
    reliability_penalty = Column(Numeric(3, 2), default=0.00)
    consecutive_failures = Column(Integer, default=0)
    last_success_at = Column(DateTime(timezone=True))
