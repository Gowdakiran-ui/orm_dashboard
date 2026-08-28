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

def onboard_client(db: Session, onboarding_data: ClientOnboarding) -> Client:
    # Client name is deliberately NOT unique (TASK_CLIENT_NAME.md) --
    # isolation in this system is per client_id via user_client_access, not
    # per name. Two different users each onboarding a company called
    # "Anthropic" are two unrelated tenants that happen to share a display
    # name; rejecting the second one as "already exists" was wrong (it was
    # checking every OTHER user's clients too, not just the caller's own).
    # 1. Create the Client
    db_client = Client(
        name=onboarding_data.name,
        industry=onboarding_data.industry
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)

    # Steps 2-8 create the entity/keywords/feeds/source for the client just
    # committed above. create_entity/add_alias/generate_keywords_for_entity
    # each commit independently (they're shared with entities.py's
    # standalone single-entity endpoints, which need that), so a failure
    # partway through this block can't be undone with a plain db.rollback()
    # — anything already committed stays committed. Track what got created
    # and compensate (delete it) on failure instead, so onboarding ends in
    # either a fully-provisioned client or a client with no orphaned
    # half-provisioned entities (TASK.md Phase 4 item 4).
    created_entity_ids = []
    try:
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
        created_entity_ids.append(db_entity.id)

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
                is_active=True,
                client_id=db_client.id
            )
            db.add(db_feed)

        # 5b. Also provision GDELT DOC 2.0 and HN Algolia json_api feeds for this
        # entity (Part B4). Conservative poll interval: GDELT's confirmed live
        # rate limit is ~1 request/5s, HN Algolia has no documented hard limit —
        # 60 minutes is well above either floor.
        gdelt_url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={sanitized_name}&mode=artlist&format=json&maxrecords=50"
        existing_gdelt_feed = db.query(RSSFeed).filter(RSSFeed.feed_url == gdelt_url).first()
        if not existing_gdelt_feed:
            db.add(RSSFeed(
                feed_name=f"{onboarding_data.primary_entity_name} GDELT Feed",
                feed_url=gdelt_url,
                category="News",
                poll_interval_minutes=60,
                is_active=True,
                client_id=db_client.id,
                source_type="json_api",
                source_format="gdelt_json"
            ))

        hn_url = f"https://hn.algolia.com/api/v1/search?query={sanitized_name}&tags=story"
        existing_hn_feed = db.query(RSSFeed).filter(RSSFeed.feed_url == hn_url).first()
        if not existing_hn_feed:
            db.add(RSSFeed(
                feed_name=f"{onboarding_data.primary_entity_name} HN Algolia Feed",
                feed_url=hn_url,
                category="News",
                poll_interval_minutes=60,
                is_active=True,
                client_id=db_client.id,
                source_type="json_api",
                source_format="hn_algolia_json"
            ))

        # 6. Automatically create Collection Source (in the sources table)
        from app.models.source import Source, SourceCategory
        # Find or create a category for RSS. Shared reference-data row (not
        # client-specific) — its own commit is intentionally left as-is:
        # rolling it back on a later failure could pull the category out
        # from under other clients' concurrently-committed sources.
        cat = db.query(SourceCategory).filter(SourceCategory.name == "RSS News").first()
        if not cat:
            cat = SourceCategory(name="RSS News", base_reliability_score=1.0)
            db.add(cat)
            db.commit()
            db.refresh(cat)

        # Check if this source url already exists before adding -- same
        # reasoning as the RSSFeed checks above: sources has no client_id at
        # all (it's shared reference data, like SourceCategory just above),
        # so it was always meant to be deduplicated by url. This particular
        # insert was the one spot that skipped that check, which stayed
        # unreachable while client names were globally unique (the url is
        # built from the entity name) -- surfaced as a hard uq_sources_url
        # crash the moment two differently-owned clients share a name
        # (TASK_CLIENT_NAME.md; confirmed live).
        existing_source = db.query(Source).filter(Source.url == google_news_url).first()
        if not existing_source:
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
                    comp_entity = create_entity(db, comp_entity_in)
                    created_entity_ids.append(comp_entity.id)

        # 8. Automatically create Processing Configuration / Refresh matching engine
        # In our platform, the matching engine needs to reload the new active keywords
        from app.services.matching_engine import engine_instance
        engine_instance.refresh_processor(db)

        db.commit()
    except Exception as exc:
        db.rollback()
        if created_entity_ids:
            db.query(Entity).filter(Entity.id.in_(created_entity_ids)).delete(synchronize_session=False)
            db.commit()
        logger.error("client_onboarding_failed", client_id=str(db_client.id), stage="entity_setup", error=str(exc))
        raise HTTPException(status_code=500, detail="Client onboarding failed while provisioning the primary entity; changes were rolled back.")

    return db_client

def get_clients(db: Session, skip: int = 0, limit: int = 100, search: Optional[str] = None, client_ids=None):
    query = db.query(Client)
    if client_ids is not None:
        # Tenant-authorization scoping (TASK_AUTH.md fix #4) -- callers pass
        # the requesting user's granted client_ids; None (not an empty list)
        # means "no scoping requested", used only by internal/administrative
        # callers, if any are ever added.
        query = query.filter(Client.id.in_(client_ids))
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
    client_feeds = db.query(RSSFeed).filter(RSSFeed.client_id == client_id).all()
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

        if doc_ids_with_mentions:
            # Single set-based query instead of one query per document (was
            # O(n) round trips -- with real clients running 300-470+ mentioned
            # documents, this alone caused the delete endpoint to exceed the
            # frontend's 15s timeout, especially over Render's WAN latency).
            other_client_doc_ids = {
                row.document_id
                for row in db.query(EntityMention.document_id).join(Entity).filter(
                    EntityMention.document_id.in_(doc_ids_with_mentions),
                    Entity.client_id != client_id
                ).distinct().all()
            }
            doc_ids_to_delete |= (doc_ids_with_mentions - other_client_doc_ids)

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

    # Snapshot counts before deletion for the audit trail.
    # Combined into a single round trip (was 7 separate queries) -- each
    # round trip to Render's WAN-latency DB adds up fast, and this endpoint
    # already had one timeout bug from too many sequential queries.
    audit_counts = db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM narratives WHERE client_id=:cid) AS narratives,
            (SELECT COUNT(*) FROM risk_events WHERE client_id=:cid) AS risk_events,
            (SELECT COUNT(*) FROM alerts WHERE client_id=:cid) AS alerts,
            (SELECT COUNT(*) FROM reputation_scores WHERE client_id=:cid) AS reputation_scores,
            (SELECT COUNT(*) FROM competitor_benchmarks WHERE client_id=:cid) AS competitor_benchmarks,
            (SELECT COUNT(*) FROM executive_reputation_scores WHERE client_id=:cid) AS executive_reputation_scores,
            (SELECT COUNT(*) FROM trend_events WHERE client_id=:cid) AS trend_events
    """), {"cid": str(client_id)}).one()

    pre_counts = {
        "entities":                  len(entities),
        "narratives":                audit_counts.narratives,
        "risk_events":               audit_counts.risk_events,
        "alerts":                    audit_counts.alerts,
        "reputation_scores":         audit_counts.reputation_scores,
        "competitor_benchmarks":     audit_counts.competitor_benchmarks,
        "executive_reputation_scores": audit_counts.executive_reputation_scores,
        "trend_events":              audit_counts.trend_events,
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
