import uuid
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.db import Base

class RSSFeed(Base):
    __tablename__ = "rss_feeds"
    # migrations/0005: was UNIQUE(feed_url) alone, which meant two different
    # clients whose entity names sanitize to the same query string (e.g. two
    # "Tesla" clients) silently collided -- the second onboard_client() call's
    # existing_feed check matched the first client's row and skipped
    # provisioning entirely, leaving the second client with zero feeds and no
    # error. Scoped to (client_id, feed_url) so each client gets its own row
    # even when the generated URL text matches.
    __table_args__ = (
        UniqueConstraint("client_id", "feed_url", name="uq_rss_feeds_client_id_feed_url"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feed_name = Column(String(255), nullable=False)
    feed_url = Column(String(1024), nullable=False)
    category = Column(String(50)) # News, Business, Technology, Cybersecurity, Government, Press Release
    poll_interval_minutes = Column(Integer, default=60)

    # Owning client. Nullable: topical_global feeds have no single owning client.
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    # entity_search (per-client), topical_global, or json_api
    source_type = Column(String(20), nullable=False, default="entity_search")
    # Wire format an adapter must parse: rss, gdelt_json, hn_algolia_json
    source_format = Column(String(20), nullable=False, default="rss")
    is_active = Column(Boolean, default=True)
    last_polled_at = Column(DateTime(timezone=True))
    
    # Position tracking
    last_entry_guid = Column(Text)
    last_entry_published_at = Column(DateTime(timezone=True))
    
    # Reliability metadata
    reliability_score = Column(Float, default=1.0)
    
    # Configuration
    extract_full_article = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
