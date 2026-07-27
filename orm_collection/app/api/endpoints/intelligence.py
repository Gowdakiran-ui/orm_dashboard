from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, Any

from app.core.db import get_db
from app.models.document import Document
from app.models.topic import DocumentTopic
from app.models.entity import EntityMention

from app.models.sentiment import DocumentSentiment, EntitySentiment

router = APIRouter()

@router.get("/{document_id}/analysis", response_model=Dict[str, Any])
def get_document_analysis(document_id: UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get topics
    doc_topics = db.query(DocumentTopic).filter(DocumentTopic.document_id == document_id).all()
    topics_data = [{"topic_name": dt.topic.name, "confidence_score": dt.confidence_score} for dt in doc_topics]

    # Get entities
    mentions = db.query(EntityMention).filter(EntityMention.document_id == document_id).all()
    entities_data = [{"entity_name": m.entity.name, "role": m.role, "mentions": m.mention_count} for m in mentions]

    # Get document sentiment
    doc_sentiments = db.query(DocumentSentiment).filter(DocumentSentiment.document_id == document_id).all()
    sentiment_data = [{"label": ds.sentiment_label, "score": ds.sentiment_score, "weighted_score": ds.weighted_sentiment_score} for ds in doc_sentiments]

    # Get entity sentiment
    ent_sentiments = db.query(EntitySentiment).filter(EntitySentiment.document_id == document_id).all()
    entity_sentiment_data = [{"entity_name": es.entity.name, "label": es.sentiment_label, "score": es.sentiment_score} for es in ent_sentiments]

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
def get_document_risk(document_id: UUID, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    events = db.query(RiskEvent).filter(RiskEvent.document_id == document_id).all()
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
