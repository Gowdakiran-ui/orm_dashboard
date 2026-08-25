import spacy
import structlog
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.entity import Entity, EntityMention
from app.models.document import Document
from app.services.matching_engine import engine_instance, get_client_boost_terms
from app.services.intelligence.entity_discovery import entity_discovery_engine

logger = structlog.get_logger()

class EntityExtractor:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError as e:
            self.nlp = None
            logger.critical(
                "spacy_model_not_loaded",
                model="en_core_web_sm",
                reason=str(e),
                effect="NER discovery will return empty candidates silently."
            )

    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        if not self.nlp:
            return []
        
        doc = self.nlp(text)
        extracted = []
        for ent in doc.ents:
            if ent.label_ in ["ORG", "PERSON", "PRODUCT", "GPE"]:
                extracted.append({
                    "name": ent.text,
                    "label": ent.label_
                })
        return extracted

    def process_document(self, db: Session, document_id: str, client_id: str = None):
        """
        Process document with enhanced entity discovery pipeline:
        1. Match existing entities using keyword matching
        2. Run NER-based discovery to create candidates for unknown entities
        """
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return
        if not document.normalized_content:
            # Without this, a document with empty (not NULL) normalized_content
            # returns here without ever reaching the processing_status="MATCHED"/
            # "SKIPPED" assignment below, leaving it stuck at "PROCESSING"
            # (set by the caller, execute_document_intelligence_sync) forever —
            # found live via a document permanently stuck this way.
            document.processing_status = "SKIPPED"
            db.commit()
            return
        
        # Step 1: Match existing entities using keyword matching
        if not engine_instance.is_loaded:
            engine_instance.refresh_processor(db)
            
        matches = engine_instance.find_matches(document.normalized_content)
        
        # Clear existing mentions for this document to avoid duplicates on reprocessing
        db.query(EntityMention).filter(EntityMention.document_id == document.id).delete()
        
        unique_entities = set()
        matched_client_ids = set()
        # M6-F1: per-client executive/product boost terms, batched once per
        # client_id (not per match) -- see get_client_boost_terms.
        boost_terms_by_client = {}
        for m in matches:
            entity_id = m["entity_id"]
            if entity_id not in unique_entities:
                unique_entities.add(entity_id)
                entity = db.query(Entity).filter(Entity.id == entity_id).first()
                if not entity:
                    continue

                matched_client_ids.add(entity.client_id)

                if entity.client_id not in boost_terms_by_client:
                    boost_terms_by_client[entity.client_id] = get_client_boost_terms(db, entity.client_id)
                boost_terms = boost_terms_by_client[entity.client_id]

                # Evaluate match accuracy
                accuracy_meta = engine_instance.evaluate_match_accuracy(
                    document.normalized_content, m, entity.domain, entity.name,
                    executive_terms=boost_terms["executive_terms"],
                    product_terms=boost_terms["product_terms"],
                    entity_industry=entity.industry
                )
                
                if accuracy_meta["status"] == "accepted":
                    mention = EntityMention(
                        document_id=document.id,
                        entity_id=entity.id,
                        # "rejected_competitor" (A3) is still an organization —
                        # without it here, a reclassified entity's mentions would
                        # be labelled PERSON in the /intelligence response.
                        role="ORG" if entity.entity_type in ["brand", "competitor", "product", "rejected_competitor"] else "PERSON",
                        mention_count=1,
                        confidence_score=accuracy_meta["final_confidence"]
                    )
                    db.add(mention)
        
        # Step 2: Run NER-based entity discovery to create candidates
        clients_to_run = [client_id] if client_id else list(matched_client_ids)
        
        if not clients_to_run:
            logger.error(
                "entity_discovery_skipped_no_client_id",
                document_id=document_id,
                client_id=client_id,
                matched_client_ids=list(matched_client_ids),
                reason="client_id is None and no entities matched"
            )
        
        discovery_results_list = []
        for cid in clients_to_run:
            if cid:
                discovery_results = entity_discovery_engine.process_document(
                    db, document_id, str(cid)
                )
                if discovery_results:
                    discovery_results["client_id"] = str(cid)
                    discovery_results_list.append(discovery_results)
        
        has_candidates = any(res.get("executive_candidates_created", 0) > 0 or res.get("competitor_candidates_created", 0) > 0 for res in discovery_results_list)
        if not matched_client_ids and not has_candidates:
            document.processing_status = "SKIPPED"
        else:
            document.processing_status = "MATCHED"
        db.commit()
        return list(clients_to_run), discovery_results_list
