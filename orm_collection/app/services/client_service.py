from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
from uuid import UUID
from app.models.client import Client
from app.models.entity import Entity
from app.schemas.client import ClientOnboarding, ClientCreate
from app.schemas.entity import EntityCreate
from app.services.entity_service import create_entity, add_alias
from app.services.keyword_service import generate_keywords_for_entity
import structlog
from app.models.rss_feed import RSSFeed

logger = structlog.get_logger()

import re

def normalize_client_name(name: str) -> str:
    # Lowercase and strip whitespace
    n = name.lower().strip()
    # Remove punctuation
    n = re.sub(r'[^\w\s]', '', n)
    # Remove common corporate suffixes (word bounded)
    n = re.sub(r'\b(inc|ltd|llc|corp|corporation|co)\b', '', n)
    # Normalize internal whitespace
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def onboard_client(db: Session, onboarding_data: ClientOnboarding) -> Client:
    # 0. Check for Client Uniqueness (Phase 6.4)
    normalized_new = normalize_client_name(onboarding_data.name)
    existing_clients = db.query(Client).all()
    for c in existing_clients:
        if normalize_client_name(c.name) == normalized_new:
            raise HTTPException(status_code=400, detail="Client with a similar name already exists.")

    # 1. Create the Client
    db_client = Client(
        name=onboarding_data.name,
        industry=onboarding_data.industry
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)

    # 2. Create the Primary Entity
    entity_in = EntityCreate(
        client_id=db_client.id,
        name=onboarding_data.primary_entity_name,
        entity_type="brand",
        website=onboarding_data.website,
        domain=onboarding_data.domain,
        ticker_symbol=onboarding_data.ticker_symbol,
        industry=onboarding_data.industry
    )
    db_entity = create_entity(db, entity_in)

    # 3. Add aliases if relevant (e.g. ticker symbol)
    if onboarding_data.ticker_symbol:
        add_alias(db, db_entity.id, onboarding_data.ticker_symbol)

    # 4. Generate keywords
    generate_keywords_for_entity(db, str(db_entity.id), onboarding_data.primary_entity_name)

    # 5. Automatically create RSS Feeds & Google News queries for this entity/client
    # Let's create an RSS feed for general news related to the entity
    # We will generate search queries for Google News RSS:
    # URL format for Google News: https://news.google.com/rss/search?q={query}
    # We will sanitize the query string.
    sanitized_name = onboarding_data.primary_entity_name.replace(" ", "+")
    google_news_url = f"https://news.google.com/rss/search?q={sanitized_name}+OR+{onboarding_data.domain or sanitized_name}"
    
    # Check if this feed url already exists before adding
    existing_feed = db.query(RSSFeed).filter(RSSFeed.feed_url == google_news_url).first()
    if not existing_feed:
        db_feed = RSSFeed(
            feed_name=f"{onboarding_data.primary_entity_name} Google News Feed",
            feed_url=google_news_url,
            category="News",
            poll_interval_minutes=60,
            is_active=True
        )
        db.add(db_feed)

    # 6. Automatically create Collection Source (in the sources table)
    from app.models.source import Source, SourceCategory
    # Find or create a category for RSS
    cat = db.query(SourceCategory).filter(SourceCategory.name == "RSS News").first()
    if not cat:
        cat = SourceCategory(name="RSS News", base_reliability_score=1.0)
        db.add(cat)
        db.commit()
        db.refresh(cat)

    db_source = Source(
        category_id=cat.id,
        name=f"{onboarding_data.primary_entity_name} RSS Source",
        source_type="rss",
        url=google_news_url,
        schedule_cron="0 * * * *",
        is_active=True
    )
    db.add(db_source)

    # 7. Create real competitors if provided in onboarding data
    if hasattr(onboarding_data, 'competitors') and onboarding_data.competitors:
        for comp_data in onboarding_data.competitors:
            # Check if competitor already exists by name
            existing_comp = db.query(Entity).filter(
                Entity.client_id == db_client.id,
                Entity.name == comp_data.name,
                Entity.entity_type == "competitor"
            ).first()
            
            if not existing_comp:
                comp_entity_in = EntityCreate(
                    client_id=db_client.id,
                    name=comp_data.name,
                    entity_type="competitor",
                    website=comp_data.get('website'),
                    domain=comp_data.get('domain'),
                    ticker_symbol=comp_data.get('ticker_symbol'),
                    industry=onboarding_data.industry
                )
                create_entity(db, comp_entity_in)

    # 8. Automatically create Processing Configuration / Refresh matching engine
    # In our platform, the matching engine needs to reload the new active keywords
    from app.services.matching_engine import engine_instance
    engine_instance.refresh_processor(db)

    db.commit()
    return db_client

def get_clients(db: Session, skip: int = 0, limit: int = 100, search: Optional[str] = None):
    query = db.query(Client)
    if search:
        query = query.filter(Client.name.ilike(f"%{search}%"))
    return query.order_by(Client.name, Client.id).offset(skip).limit(limit).all()

def delete_client(db: Session, client_id: UUID) -> dict:
    """
    Deletes a client and all associated intelligence data.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found.")

    client_name = client.name

    from app.models.rss_feed import RSSFeed
    from app.models.source import Source
    from app.models.document import Document
    from app.models.entity import Entity, EntityMention
    from app.utils.redis_client import redis_client

    # Find client-specific feeds and sources
    feeds = db.query(RSSFeed).all()
    client_feeds = [f for f in feeds if client_name.lower() in f.feed_name.lower()]
    feed_urls = [f.feed_url for f in client_feeds]
    sources = db.query(Source).filter(Source.url.in_(feed_urls)).all()
    source_ids = [s.id for s in sources]

    # Find entities
    entities = db.query(Entity).filter(Entity.client_id == client_id).all()
    entity_ids = [e.id for e in entities]

    # Find documents to delete:
    # 1. Documents whose source_id matches any client sources
    docs_from_sources = db.query(Document).filter(Document.source_id.in_(source_ids)).all()
    doc_ids_to_delete = {d.id for d in docs_from_sources}

    # 2. Documents matched with this client's entities and NOT matched with other clients
    if entity_ids:
        client_doc_mentions = db.query(EntityMention.document_id).filter(
            EntityMention.entity_id.in_(entity_ids)
        ).distinct().all()
        doc_ids_with_mentions = {m.document_id for m in client_doc_mentions}
        
        for doc_id in doc_ids_with_mentions:
            other_mentions_count = db.query(EntityMention).join(Entity).filter(
                EntityMention.document_id == doc_id,
                Entity.client_id != client_id
            ).count()
            if other_mentions_count == 0:
                doc_ids_to_delete.add(doc_id)

    # Perform Deletion of Documents
    deleted_docs_count = 0
    if doc_ids_to_delete:
        deleted_docs_count = db.query(Document).filter(Document.id.in_(list(doc_ids_to_delete))).delete(synchronize_session=False)

    # Perform Deletion of Feeds and Sources
    deleted_feeds_count = len(client_feeds)
    for f in client_feeds:
        db.delete(f)
    
    deleted_sources_count = len(sources)
    for s in sources:
        db.delete(s)

    # Delete pipeline states
    from app.models.trend_state import TrendClientState
    from app.models.risk_state import RiskClientState
    from app.models.alert_state import AlertClientState
    from app.models.client_processing_summary import ClientProcessingSummary
    
    db.query(TrendClientState).filter(TrendClientState.client_id == client_id).delete(synchronize_session=False)
    db.query(RiskClientState).filter(RiskClientState.client_id == client_id).delete(synchronize_session=False)
    db.query(AlertClientState).filter(AlertClientState.client_id == client_id).delete(synchronize_session=False)
    db.query(ClientProcessingSummary).filter(ClientProcessingSummary.client_id == client_id).delete(synchronize_session=False)

    # Snapshot counts before deletion for the audit trail
    pre_counts = {
        "entities":                  len(entities),
        "narratives":                db.execute(text("SELECT COUNT(*) FROM narratives WHERE client_id=:cid"), {"cid": str(client_id)}).scalar(),
        "risk_events":               db.execute(text("SELECT COUNT(*) FROM risk_events WHERE client_id=:cid"), {"cid": str(client_id)}).scalar(),
        "alerts":                    db.execute(text("SELECT COUNT(*) FROM alerts WHERE client_id=:cid"), {"cid": str(client_id)}).scalar(),
        "reputation_scores":         db.execute(text("SELECT COUNT(*) FROM reputation_scores WHERE client_id=:cid"), {"cid": str(client_id)}).scalar(),
        "competitor_benchmarks":     db.execute(text("SELECT COUNT(*) FROM competitor_benchmarks WHERE client_id=:cid"), {"cid": str(client_id)}).scalar(),
        "executive_reputation_scores": db.execute(text("SELECT COUNT(*) FROM executive_reputation_scores WHERE client_id=:cid"), {"cid": str(client_id)}).scalar(),
        "trend_events":              db.execute(text("SELECT COUNT(*) FROM trend_events WHERE client_id=:cid"), {"cid": str(client_id)}).scalar(),
        "deleted_feeds":             deleted_feeds_count,
        "deleted_sources":           deleted_sources_count,
        "deleted_documents":         deleted_docs_count,
    }

    # Remove Redis lock keys
    try:
        redis_client.delete(f"pipeline:running:{client_id}")
        redis_client.delete(f"pipeline:progress:{client_id}")
    except Exception as re:
        logger.warning("redis_delete_failed", error=str(re))

    # Deleting the client cascades remaining entities, etc.
    db.delete(client)
    db.commit()

    logger.info("client_deleted", client_id=str(client_id), client_name=client_name, pre_counts=pre_counts)

    return {
        "status": "deleted",
        "client_id": str(client_id),
        "client_name": client_name,
        "records_purged": pre_counts
    }
