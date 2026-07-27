import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.db import Base

class Entity(Base):
    __tablename__ = "entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    entity_type = Column(String(50)) # 'brand', 'person', 'product', 'competitor'
    
    # Verification Fields
    website = Column(String(255))
    domain = Column(String(255))
    linkedin_url = Column(String(1024))
    ticker_symbol = Column(String(20))
    industry = Column(String(100))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    keywords = relationship("EntityKeyword", back_populates="entity", cascade="all, delete-orphan")
    aliases = relationship("EntityAlias", back_populates="entity", cascade="all, delete-orphan")

class EntityAlias(Base):
    __tablename__ = "entity_aliases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    alias_text = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entity = relationship("Entity", back_populates="aliases")

class EntityKeyword(Base):
    __tablename__ = "entity_keywords"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword_text = Column(String(255), nullable=False, index=True)
    match_type = Column(String(20), default="exact") # 'exact', 'phrase', 'regex'
    category = Column(String(50), nullable=False, default="PRIMARY") # PRIMARY, ALIAS, EXECUTIVE, PRODUCT, COMPETITOR, RISK
    priority = Column(Integer, default=1)
    search_frequency_minutes = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)

    entity = relationship("Entity", back_populates="keywords")

class EntityMention(Base):
    __tablename__ = "entity_mentions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50))
    mention_count = Column(Integer, default=1)
    confidence_score = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entity = relationship("Entity")
