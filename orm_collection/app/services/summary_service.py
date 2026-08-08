import os
import sys

# Add project root to python path
import pathlib
project_root = str(pathlib.Path(__file__).parent.parent.parent)
sys.path.insert(0, project_root)

from app.core.db import SessionLocal
from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.document import Document, DocumentMatch
from app.models.topic import DocumentTopic
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.risk import RiskEvent
from app.models.alert import Alert
from app.models.narrative import Narrative
from app.models.reputation import ReputationScore
from app.models.client_processing_summary import ClientProcessingSummary
from sqlalchemy import func
from datetime import datetime, timezone

def update_client_summaries():
    print("Updating client processing summaries...")
    db = SessionLocal()
    try:
        clients = db.query(Client).all()
        for client in clients:
            # Find primary entity for client
            entity = db.query(Entity).filter(Entity.client_id == client.id, Entity.entity_type == "brand").first()
            entity_id = entity.id if entity else None
            
            # Count metrics
            # Document collection is mapped via source -> source_category -> clients (or similar)
            # In our system: source_id -> sources. category_id -> source_categories. client_id is not in category but we can count matches!
            # Since matches are explicitly tied to the client's entity:
            entity_matches_count = 0
            if entity_id:
                entity_matches_count = db.query(DocumentMatch).filter(DocumentMatch.matched_entity_id == entity_id).count()
                
            # Documents collected for this client = unique documents matched to this client's entities
            # (In a simplified model, or we can count unique document matches)
            documents_collected = 0
            if entity_id:
                documents_collected = db.query(func.count(func.distinct(DocumentMatch.document_id))).filter(DocumentMatch.matched_entity_id == entity_id).scalar() or 0
                
            # Documents processed successfully (with completed status)
            documents_processed = documents_collected # simplify or count completed ones
            
            # Intelligence elements
            topics_generated = 0
            sentiments_generated = 0
            if entity_id:
                # Document matches for this entity
                doc_ids = db.query(DocumentMatch.document_id).filter(DocumentMatch.matched_entity_id == entity_id).subquery()
                topics_generated = db.query(DocumentTopic).filter(DocumentTopic.document_id.in_(doc_ids)).count()
                sentiments_generated = db.query(DocumentSentiment).filter(DocumentSentiment.document_id.in_(doc_ids)).count()
                
            risks_generated = db.query(RiskEvent).filter(RiskEvent.client_id == client.id).count()
            alerts_generated = db.query(Alert).filter(Alert.client_id == client.id).count()
            narratives_generated = db.query(Narrative).filter(Narrative.client_id == client.id).count()
            
            # Get latest reputation score
            latest_rep = db.query(ReputationScore).filter(ReputationScore.client_id == client.id).order_by(ReputationScore.created_at.desc()).first()
            reputation_score = latest_rep.score if latest_rep else 0.0
            
            # Upsert
            summary = db.query(ClientProcessingSummary).filter(ClientProcessingSummary.client_id == client.id).first()
            if not summary:
                summary = ClientProcessingSummary(
                    client_id=client.id,
                    client_name=client.name,
                    documents_collected=documents_collected,
                    documents_processed=documents_processed,
                    entity_matches=entity_matches_count,
                    topics_generated=topics_generated,
                    sentiments_generated=sentiments_generated,
                    risks_generated=risks_generated,
                    alerts_generated=alerts_generated,
                    narratives_generated=narratives_generated,
                    reputation_score=reputation_score,
                    last_processed_at=datetime.now(timezone.utc)
                )
                db.add(summary)
            else:
                summary.documents_collected = documents_collected
                summary.documents_processed = documents_processed
                summary.entity_matches = entity_matches_count
                summary.topics_generated = topics_generated
                summary.sentiments_generated = sentiments_generated
                summary.risks_generated = risks_generated
                summary.alerts_generated = alerts_generated
                summary.narratives_generated = narratives_generated
                summary.reputation_score = reputation_score
                summary.last_processed_at = datetime.now(timezone.utc)
                
            print(f"Client {client.name}: Collected={documents_collected}, Matches={entity_matches_count}, Rep={reputation_score}")
            
        db.commit()
        print("Successfully updated all client processing summaries.")
    except Exception as e:
        db.rollback()
        print(f"Error updating summaries: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    update_client_summaries()
