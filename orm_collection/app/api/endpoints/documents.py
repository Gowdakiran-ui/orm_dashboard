from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.db import get_db
from app.schemas.document import DocumentResponse
from app.models.document import Document, DocumentMatch

router = APIRouter()


def _brand_gated_document_ids(db: Session, client_id):
    """
    Brand co-occurrence containment (xoop_ui_clarity_review.md Phase 0,
    2026-09-13): a client's own tracked person/competitor entities can be
    generic, globally-common names (e.g. Anthropic tracking "Trump", "Elon
    Musk", "Google" as competitor/person entities relevant to real Anthropic
    coverage) that also appear constantly in totally unrelated clients' own
    news. matching_engine.py's shared GlobalMatchingEngine has no check that
    the client's own brand is actually mentioned before accepting a match, so
    a document matching ONLY on one of those generic names -- zero mention of
    the client's own brand anywhere in it -- was still treated as this
    client's own document. Confirmed live: 20 100%-Tesla documents were
    showing up in Anthropic's document feed this way, matched only via
    entities like "Trump" and "Elon Musk".

    Returns the set of document ids that have an accepted match to this
    client's own entity_type='brand' OR 'product' entity, or None if the
    client has neither (an existing-data edge case that should not happen
    for an onboarded client) -- callers treat None as "don't gate", rather
    than silently returning zero documents for such a client. 'product' is
    included alongside 'brand' (not just 'brand' alone) because a client's
    own flagship product is routinely covered by name without the parent
    brand name ever appearing in the same text -- confirmed live, 24 genuine
    Anthropic articles (including two from anthropic.com itself) mention
    "Claude" but never "Anthropic", and would otherwise be false-negatived
    out of Anthropic's own document feed by a brand-only gate.

    This is a targeted containment in this read path, not a fix to
    matching_engine.py itself (a platform-wide, shared-scoring change across
    every client that needs real regression testing before it can be
    trusted).
    """
    from app.models.entity import Entity

    brand_or_product_ids = [
        r[0] for r in db.query(Entity.id).filter(
            Entity.client_id == client_id, Entity.entity_type.in_(("brand", "product"))
        ).all()
    ]
    if not brand_or_product_ids:
        return None
    rows = db.query(DocumentMatch.document_id).filter(
        DocumentMatch.matched_entity_id.in_(brand_or_product_ids)
    ).all()
    return {r[0] for r in rows}


def get_client_visible_documents(db: Session, client_id, skip: int = 0, limit: int = 100):
    """
    The exact document set Risk Center (and every other page that consumes
    `documents`) can ever show for a client: matched documents ordered by
    recency, capped at 500. Single source of truth -- read_client_documents
    below calls this instead of inlining the query, and
    ai_summary_engine.py's Risk Event sweep imports and calls this same
    function (with the same limit=500 the frontend's own fetchDocuments()
    always requests) rather than a separately-written copy. A change to
    this cap or ordering is then automatically inherited everywhere instead
    of requiring a second manual fix later -- this project has already been
    bitten once by two places computing "the same thing" slightly
    differently and silently drifting apart (the Risk-Matrix Likelihood
    formula bug).
    """
    from app.models.entity import Entity
    limit = min(limit, 500)  # hard ceiling — caller-supplied limit was previously unbounded
    query = (
        db.query(Document)
        .join(DocumentMatch)
        .join(Entity)
        .filter(Entity.client_id == client_id)
    )
    brand_doc_ids = _brand_gated_document_ids(db, client_id)
    if brand_doc_ids is not None:
        query = query.filter(Document.id.in_(brand_doc_ids))
    return (
        query
        .distinct()
        .order_by(Document.published_at.desc(), Document.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/", response_model=List[DocumentResponse])
def read_documents(client_id: UUID, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    limit = min(limit, 500)  # hard ceiling — caller-supplied limit was previously unbounded
    # Scoped by client_id (API_FORENSICS.md / FINAL.md #1) — previously
    # returned every document in the database regardless of caller, unlike
    # every sibling endpoint in this file. Matches the join pattern already
    # used correctly in GET /{document_id} and GET /client/{client_id} below.
    from app.models.entity import Entity
    query = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Entity.client_id == client_id
    )
    brand_doc_ids = _brand_gated_document_ids(db, client_id)
    if brand_doc_ids is not None:
        query = query.filter(Document.id.in_(brand_doc_ids))
    return query.distinct().order_by(Document.published_at.desc(), Document.id.desc()).offset(skip).limit(limit).all()

@router.get("/{document_id}")
def read_document(document_id: UUID, client_id: UUID, db: Session = Depends(get_db)):
    from app.models.entity import Entity, EntityMention

    # Scope by client_id — a document is only returned if it's actually
    # matched to an entity belonging to the requesting client (API_FORENSICS.md
    # Section 2 / TASK.md Phase 2 item 2). Matches the join pattern already
    # used correctly in GET /client/{client_id} below.
    query = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Document.id == document_id,
        Entity.client_id == client_id,
    )
    brand_doc_ids = _brand_gated_document_ids(db, client_id)
    if brand_doc_ids is not None:
        query = query.filter(Document.id.in_(brand_doc_ids))
    doc = query.distinct().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.models.source import Source
    from app.models.sentiment import DocumentSentiment
    from app.models.risk import RiskEvent
    from app.models.topic import DocumentTopic
    from app.models.alert import Alert
    
    source = db.query(Source).filter(Source.id == doc.source_id).first()
    source_name = getattr(source, "name", "RSS Feed") if source else "RSS Feed"
    
    sentiment_rec = db.query(DocumentSentiment).filter(DocumentSentiment.document_id == doc.id).first()
    sentiment_val = getattr(sentiment_rec, "sentiment_score", 0.0) if sentiment_rec else 0.0
    
    # Scoped by client_id and take the highest-scoring entity match --
    # unscoped .first() previously returned an arbitrary RiskEvent row for
    # this document_id, including ones belonging to OTHER clients that also
    # matched the same document (e.g. a shared entity name), or an arbitrary
    # one of this client's own entities when more than one matched. Confirmed
    # live: doc b1aedae6-...-5479 has a stale OpenAI risk_events row (39.58)
    # and Duolingo's own row (35.41) -- Duolingo's detail view was showing
    # OpenAI's score. risk_engine.py's own upsert already scopes by
    # client_id; this endpoint just wasn't matching that scoping.
    # Risk Center shows the client's own risk, not a tracked competitor's --
    # RiskEvent rows exist per tracked entity (brand/competitor/person) since
    # benchmark_engine.py needs competitor-scoped risk for its own comparison
    # feature. Excluding entity_type='competitor' here only (read side, not
    # at creation) keeps that feature intact while stopping e.g. a
    # competitor's own fraud story from being attributed to this client as
    # its own risk. entity_id IS NULL is kept in (not excluded) since a
    # RiskEvent without an entity association was never entity-scoped to
    # begin with.
    risk_rec = db.query(RiskEvent).outerjoin(Entity, Entity.id == RiskEvent.entity_id).filter(
        RiskEvent.document_id == doc.id,
        RiskEvent.client_id == client_id,
        or_(Entity.entity_type != "competitor", Entity.entity_type.is_(None), RiskEvent.entity_id.is_(None)),
    ).order_by(RiskEvent.risk_score.desc()).first()
    risk_val = getattr(risk_rec, "risk_score", 0.0) if risk_rec else 0.0
    risk_explainability = getattr(risk_rec, "explainability", None) if risk_rec else None
    
    # Highest-confidence topic, not an arbitrary DB-order row -- a document
    # can have several DocumentTopic rows (2026-09-20 investigation), and an
    # unordered .first() was surfacing whichever one Postgres happened to
    # return first, not the classifier's own top-scoring topic.
    doc_topic = db.query(DocumentTopic).filter(DocumentTopic.document_id == doc.id).order_by(DocumentTopic.confidence_score.desc()).first()
    topic_name = "General"
    if doc_topic and doc_topic.topic:
        topic_name = getattr(doc_topic.topic, "name", "General")
    
    mentions = db.query(EntityMention).filter(EntityMention.document_id == doc.id).all()
    entities = [{"name": getattr(m.entity, "name", "Unknown")} for m in mentions if m.entity]
    
    topic_confidence = getattr(doc_topic, "confidence_score", getattr(doc_topic, "confidence", None)) if doc_topic else None
    topics = [{"name": topic_name, "confidence": topic_confidence}]
    
    alert_rec = db.query(Alert).filter(Alert.document_id == doc.id).first()
    alert_data = {
        "title": getattr(alert_rec, "title", "Alert"),
        "severity": getattr(alert_rec, "severity", "INFO")
    } if alert_rec else None
    
    rep_impact = f"{'+' if sentiment_val >= 0 else ''}{sentiment_val * 10:.1f}"
    
    return {
        "id": str(doc.id),
        "title": doc.title or source_name,
        "source_id": source_name,
        "url": doc.url,
        "normalized_content": doc.normalized_content,
        "entities": entities,
        "topics": topics,
        "sentiment": sentiment_val,
        "risk": round(risk_val),  # was int() -- truncated toward zero, which
        # can misclassify a score just above a severity threshold (e.g.
        # 75.4 -> 75 reads as HIGH under the <=75 rule instead of CRITICAL)
        "risk_explainability": risk_explainability,
        "alert": alert_data,
        "reputation_impact": rep_impact
    }

def _build_document_responses(db: Session, client_id, docs: List[Document]) -> list:
    """
    Shared enrichment: turns a list of already-fetched Document rows into
    the exact response shape the frontend's `documents` array expects
    (id/title/source/timestamp/sentiment/risk/topic/...). Used by
    both read_client_documents (the main 500-most-recent window) and
    read_client_documents_by_ids (the targeted id-based fallback) so the
    two paths can never silently drift into different shapes for the same
    fields -- this project has already been bitten once by that exact
    failure mode (see get_client_visible_documents's docstring).
    """
    if not docs:
        return []

    from sqlalchemy.orm import joinedload
    from app.models.entity import Entity, EntityMention
    from app.models.source import Source
    from app.models.sentiment import DocumentSentiment
    from app.models.risk import RiskEvent
    from app.models.topic import DocumentTopic
    from app.models.document import DocumentMatch
    doc_ids = [doc.id for doc in docs]
    
    source_ids = list({doc.source_id for doc in docs if doc.source_id})
    sources = db.query(Source).filter(Source.id.in_(source_ids)).all() if source_ids else []
    source_map = {getattr(s, "id", None): getattr(s, "name", "RSS Feed") for s in sources if s}
    
    sentiments = db.query(DocumentSentiment).filter(DocumentSentiment.document_id.in_(doc_ids)).all()
    sentiment_map = {getattr(s, "document_id", None): getattr(s, "sentiment_score", 0.0) for s in sentiments if s}
    
    # Scoped by client_id, keeping the highest-scoring row per document --
    # same cross-client/cross-entity bug as read_document above: an
    # unscoped query here let a stale or foreign-client RiskEvent row for
    # the same document_id silently overwrite this client's own score in
    # the dict (confirmed live on 186 documents matched to more than one
    # client's entities, 2 of which currently carry genuinely different
    # scores).
    # Same competitor-exclusion as read_document above: a tracked
    # competitor's own risk must not be attributed to this client.
    risks = db.query(RiskEvent).outerjoin(Entity, Entity.id == RiskEvent.entity_id).filter(
        RiskEvent.document_id.in_(doc_ids),
        RiskEvent.client_id == client_id,
        or_(Entity.entity_type != "competitor", Entity.entity_type.is_(None), RiskEvent.entity_id.is_(None)),
    ).all()
    risk_map = {}
    risk_explain_map = {}
    for r in risks:
        if r.document_id not in risk_map or r.risk_score > risk_map[r.document_id]:
            risk_map[r.document_id] = r.risk_score
            risk_explain_map[r.document_id] = r.explainability
    
    # Ordered by confidence_score desc so the first-seen-per-document_id loop
    # below keeps the highest-confidence topic, not an arbitrary DB-order row
    # (2026-09-20 investigation -- Coverage-by-Topic and the Threat
    # Concentration Heatmap both consume this single flattened "topic" field).
    doc_topics = db.query(DocumentTopic).options(joinedload(DocumentTopic.topic)).filter(DocumentTopic.document_id.in_(doc_ids)).order_by(DocumentTopic.confidence_score.desc()).all()
    doc_topic_map = {}
    for dt in doc_topics:
        if dt and dt.document_id and dt.document_id not in doc_topic_map:
            doc_topic_map[dt.document_id] = dt
            
    mentions = db.query(EntityMention).options(joinedload(EntityMention.entity)).filter(EntityMention.document_id.in_(doc_ids)).all()
    mention_map = {}
    for m in mentions:
        if m and getattr(m, "entity", None):
            mention_map.setdefault(m.document_id, []).append({
                "name": getattr(m.entity, "name", "Unknown"),
                "entity_type": getattr(m.entity, "entity_type", "unknown")
            })
        
    matches = db.query(DocumentMatch).filter(DocumentMatch.document_id.in_(doc_ids)).all()
    confidence_map = {getattr(m, "document_id", None): getattr(m, "match_confidence", 1.0) for m in matches if m}

    results = []
    for doc in docs:
        if not doc:
            continue
        source_name = source_map.get(doc.source_id, "RSS Feed")
        sentiment_val = sentiment_map.get(doc.id, 0.0)
        risk_val = risk_map.get(doc.id, 0.0)
        risk_explainability = risk_explain_map.get(doc.id)
        confidence_val = confidence_map.get(doc.id, 1.0)
        
        dt = doc_topic_map.get(doc.id)
        topic_name = "General"
        if dt and dt.topic:
            topic_name = getattr(dt.topic, "name", "General")
        
        extracted_entities = mention_map.get(doc.id, [])

        rep_impact = f"{'+' if sentiment_val >= 0 else ''}{sentiment_val * 10:.1f}"

        results.append({
            "id": str(doc.id),
            "title": doc.title or source_name,
            "source": source_name,
            "timestamp": (doc.published_at or doc.collected_at).isoformat() if (doc.published_at or doc.collected_at) else None,
            "status": doc.processing_status or "COMPLETED",
            "sentiment": sentiment_val,
            "risk": round(risk_val),  # was int() -- see read_document above
            "risk_explainability": risk_explainability,
            "original_content": doc.normalized_content,
            "extracted_entities": extracted_entities,
            "topic": topic_name,
            "reputation_impact": rep_impact
        })

    return results


@router.get("/client/{client_id}")
def read_client_documents(client_id: UUID, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    limit = min(limit, 500)  # hard ceiling — caller-supplied limit was previously unbounded
    from app.models.client import Client
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    docs = get_client_visible_documents(db, client_id, skip=skip, limit=limit)
    return _build_document_responses(db, client_id, docs)


@router.get("/client/{client_id}/by-ids")
def read_client_documents_by_ids(client_id: UUID, ids: List[UUID] = Query(...), db: Session = Depends(get_db)):
    """
    Targeted fetch for a specific set of document ids -- e.g. ids that have
    aged out of this client's main 500-most-recent-document window
    (get_client_visible_documents). Scoped to this client via the same
    DocumentMatch/Entity join and brand-gating every other read here uses.

    Deliberately NOT a general search/filter endpoint: no ordering, no
    paging, no free-form query -- just "give me these specific ids back."
    An id that doesn't come back (deleted, or never belonged to this
    client) is simply absent from the response; the caller shows whatever
    is actually retrievable rather than the count being silently padded.
    """
    from app.models.client import Client
    from app.models.entity import Entity

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not ids:
        return []
    # A caller's requested id set is realistically tens of documents at
    # most; this caps the id list the same way limit=500 caps the main
    # window, so this can't become an unbounded bulk-fetch path dressed up
    # as a "by ids" lookup.
    ids = ids[:200]

    query = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Document.id.in_(ids),
        Entity.client_id == client_id,
    )
    brand_doc_ids = _brand_gated_document_ids(db, client_id)
    if brand_doc_ids is not None:
        query = query.filter(Document.id.in_(brand_doc_ids))
    docs = query.distinct().all()
    return _build_document_responses(db, client_id, docs)
