from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.db import get_db
from app.schemas.document import DocumentResponse
from app.models.document import Document, DocumentMatch

router = APIRouter()

@router.get("/", response_model=List[DocumentResponse])
def read_documents(client_id: UUID, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    limit = min(limit, 500)  # hard ceiling — caller-supplied limit was previously unbounded
    # Scoped by client_id (API_FORENSICS.md / FINAL.md #1) — previously
    # returned every document in the database regardless of caller, unlike
    # every sibling endpoint in this file. Matches the join pattern already
    # used correctly in GET /{document_id} and GET /client/{client_id} below.
    from app.models.entity import Entity
    return db.query(Document).join(DocumentMatch).join(Entity).filter(
        Entity.client_id == client_id
    ).distinct().order_by(Document.published_at.desc(), Document.id.desc()).offset(skip).limit(limit).all()

@router.get("/{document_id}")
def read_document(document_id: UUID, client_id: UUID, db: Session = Depends(get_db)):
    from app.models.entity import Entity, EntityMention

    # Scope by client_id — a document is only returned if it's actually
    # matched to an entity belonging to the requesting client (API_FORENSICS.md
    # Section 2 / TASK.md Phase 2 item 2). Matches the join pattern already
    # used correctly in GET /client/{client_id} below.
    doc = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Document.id == document_id,
        Entity.client_id == client_id,
    ).distinct().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.models.source import Source
    from app.models.sentiment import DocumentSentiment
    from app.models.risk import RiskEvent
    from app.models.topic import DocumentTopic
    from app.models.narrative import Narrative
    from app.models.alert import Alert
    
    source = db.query(Source).filter(Source.id == doc.source_id).first()
    source_name = getattr(source, "name", "RSS Feed") if source else "RSS Feed"
    
    sentiment_rec = db.query(DocumentSentiment).filter(DocumentSentiment.document_id == doc.id).first()
    sentiment_val = getattr(sentiment_rec, "sentiment_score", 0.0) if sentiment_rec else 0.0
    
    risk_rec = db.query(RiskEvent).filter(RiskEvent.document_id == doc.id).first()
    risk_val = getattr(risk_rec, "risk_score", 0.0) if risk_rec else 0.0
    
    doc_topic = db.query(DocumentTopic).filter(DocumentTopic.document_id == doc.id).first()
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
    
    narrative_name = "General Narrative"
    if doc_topic and doc_topic.topic:
        t_name = getattr(doc_topic.topic, "name", None)
        if t_name:
            narr_rec = db.query(Narrative).filter(
                Narrative.client_id == client_id,
                Narrative.narrative_name.ilike(f"%{t_name}%")
            ).first()
            if narr_rec:
                narrative_name = getattr(narr_rec, "narrative_name", "General Narrative")
            
    narrative_data = {"name": narrative_name, "mentions": 1}
    rep_impact = f"{'+' if sentiment_val >= 0 else ''}{sentiment_val * 10:.1f}"
    
    return {
        "id": str(doc.id),
        "title": doc.title or "Untitled Document",
        "source_id": source_name,
        "url": doc.url,
        "normalized_content": doc.normalized_content,
        "entities": entities,
        "topics": topics,
        "sentiment": sentiment_val,
        "risk": int(risk_val),
        "alert": alert_data,
        "narrative": narrative_data,
        "reputation_impact": rep_impact
    }

@router.get("/client/{client_id}")
def read_client_documents(client_id: UUID, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    limit = min(limit, 500)  # hard ceiling — caller-supplied limit was previously unbounded
    from app.models.client import Client
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    from app.models.entity import Entity, EntityMention
    from app.models.source import Source
    from app.models.sentiment import DocumentSentiment
    from app.models.risk import RiskEvent
    from app.models.topic import DocumentTopic
    from app.models.narrative import Narrative
    from app.models.document import DocumentMatch
    
    docs = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Entity.client_id == client_id
    ).distinct().order_by(Document.published_at.desc(), Document.id.desc()).offset(skip).limit(limit).all()
    
    if not docs:
        return []
        
    from sqlalchemy.orm import joinedload
    doc_ids = [doc.id for doc in docs]
    
    source_ids = list({doc.source_id for doc in docs if doc.source_id})
    sources = db.query(Source).filter(Source.id.in_(source_ids)).all() if source_ids else []
    source_map = {getattr(s, "id", None): getattr(s, "name", "RSS Feed") for s in sources if s}
    
    sentiments = db.query(DocumentSentiment).filter(DocumentSentiment.document_id.in_(doc_ids)).all()
    sentiment_map = {getattr(s, "document_id", None): getattr(s, "sentiment_score", 0.0) for s in sentiments if s}
    
    risks = db.query(RiskEvent).filter(RiskEvent.document_id.in_(doc_ids)).all()
    risk_map = {getattr(r, "document_id", None): getattr(r, "risk_score", 0.0) for r in risks if r}
    
    doc_topics = db.query(DocumentTopic).options(joinedload(DocumentTopic.topic)).filter(DocumentTopic.document_id.in_(doc_ids)).all()
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
        
    unique_topic_names = {dt.topic.name for dt in doc_topics if dt and dt.topic and getattr(dt.topic, "name", None)}
    narrative_cache = {}
    for t_name in unique_topic_names:
        if t_name:
            narr_rec = db.query(Narrative).filter(
                Narrative.client_id == client_id,
                Narrative.narrative_name.ilike(f"%{t_name}%")
            ).first()
            if narr_rec:
                narrative_cache[t_name] = getattr(narr_rec, "narrative_name", "General Narrative")
            
    matches = db.query(DocumentMatch).filter(DocumentMatch.document_id.in_(doc_ids)).all()
    confidence_map = {getattr(m, "document_id", None): getattr(m, "match_confidence", 1.0) for m in matches if m}

    results = []
    for doc in docs:
        if not doc:
            continue
        source_name = source_map.get(doc.source_id, "RSS Feed")
        sentiment_val = sentiment_map.get(doc.id, 0.0)
        risk_val = risk_map.get(doc.id, 0.0)
        confidence_val = confidence_map.get(doc.id, 1.0)
        
        dt = doc_topic_map.get(doc.id)
        topic_name = "General"
        if dt and dt.topic:
            topic_name = getattr(dt.topic, "name", "General")
        
        extracted_entities = mention_map.get(doc.id, [])
        
        narrative_name = "General Narrative"
        if dt and dt.topic:
            t_name = getattr(dt.topic, "name", None)
            if t_name and t_name in narrative_cache:
                narrative_name = narrative_cache[t_name]
        
        rep_impact = f"{'+' if sentiment_val >= 0 else ''}{sentiment_val * 10:.1f}"
        
        results.append({
            "id": str(doc.id),
            "title": doc.title or "Untitled Document",
            "source": source_name,
            "timestamp": (doc.published_at or doc.collected_at).isoformat() if (doc.published_at or doc.collected_at) else None,
            "status": doc.processing_status or "COMPLETED",
            "sentiment": sentiment_val,
            "risk": int(risk_val),
            "narrative": narrative_name,
            "original_content": doc.normalized_content,
            "extracted_entities": extracted_entities,
            "topic": topic_name,
            "reputation_impact": rep_impact
        })
        
    return results
