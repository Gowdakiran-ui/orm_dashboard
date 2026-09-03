from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, Any

from app.core.db import get_db
from app.models.document import Document, DocumentMatch
from app.models.topic import DocumentTopic
from app.models.entity import Entity, EntityMention

from app.models.sentiment import DocumentSentiment, EntitySentiment

router = APIRouter()

def _get_client_document(db: Session, document_id: UUID, client_id: UUID) -> Document:
    """Scope a document lookup to the requesting client (same join pattern
    as documents.py's GET /{document_id}, per TASK.md Phase 2/4)."""
    document = db.query(Document).join(DocumentMatch).join(Entity).filter(
        Document.id == document_id,
        Entity.client_id == client_id,
    ).distinct().first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document

@router.get("/{document_id}/analysis", response_model=Dict[str, Any])
def get_document_analysis(document_id: UUID, client_id: UUID, db: Session = Depends(get_db)):
    document = _get_client_document(db, document_id, client_id)

    # Get topics
    doc_topics = db.query(DocumentTopic).filter(DocumentTopic.document_id == document_id).all()
    topics_data = [{"topic_name": dt.topic.name, "confidence_score": dt.confidence_score} for dt in doc_topics]

    # Get entities
    mentions = db.query(EntityMention).filter(EntityMention.document_id == document_id).all()
    entities_data = [{"entity_name": m.entity.name, "role": m.role, "mentions": m.mention_count} for m in mentions]

    # Get document sentiment
    doc_sentiments = db.query(DocumentSentiment).filter(DocumentSentiment.document_id == document_id).all()
    sentiment_data = [{"label": ds.sentiment_label, "score": ds.sentiment_score, "weighted_score": ds.weighted_sentiment_score} for ds in doc_sentiments]

    # Get entity sentiment. EntitySentiment has no ORM relationship to
    # Entity (only a raw entity_id FK column) — look names up separately.
    ent_sentiments = db.query(EntitySentiment).filter(EntitySentiment.document_id == document_id).all()
    ent_sentiment_entity_ids = {es.entity_id for es in ent_sentiments}
    ent_sentiment_entities = db.query(Entity).filter(Entity.id.in_(ent_sentiment_entity_ids)).all() if ent_sentiment_entity_ids else []
    ent_sentiment_entity_map = {e.id: e.name for e in ent_sentiment_entities}
    entity_sentiment_data = [{"entity_name": ent_sentiment_entity_map.get(es.entity_id, "Unknown"), "label": es.sentiment_label, "score": es.sentiment_score} for es in ent_sentiments]

    return {
        "document_id": str(document.id),
        "status": document.processing_status,
        "topics": topics_data,
        "entities": entities_data,
        "document_sentiment": sentiment_data,
        "entity_sentiment": entity_sentiment_data
    }

from app.models.risk import RiskEvent

@router.get("/{document_id}/risk", response_model=Dict[str, Any])
def get_document_risk(document_id: UUID, client_id: UUID, db: Session = Depends(get_db)):
    document = _get_client_document(db, document_id, client_id)

    # Scoped by client_id -- unscoped, this returned every RiskEvent row for
    # a shared document_id, including other clients' own client_id/entity_id/
    # risk_score/confidence when the same document also matched their
    # entities. Confirmed live on 186 documents matched to more than one
    # client. Same fix as documents.py's read_document/read_client_documents.
    events = db.query(RiskEvent).filter(
        RiskEvent.document_id == document_id, RiskEvent.client_id == client_id
    ).all()
    results = []
    for e in events:
        results.append({
            "id": str(e.id),
            "client_id": str(e.client_id),
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "risk_score": e.risk_score,
            "risk_level": e.risk_level,
            "confidence_score": e.confidence_score,
            "risk_factors": e.risk_factors,
            "created_at": e.created_at.isoformat() if e.created_at else None
        })
    return {"document_id": str(document_id), "risk_events": results}
