import spacy
import uuid
import structlog
import re
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, text
import hashlib
from datetime import datetime, timezone

from app.models.entity import Entity, EntityMention, EntityKeyword, EntityAlias
from app.models.executive_candidate import ExecutiveCandidate
from app.models.competitor_candidate import CompetitorCandidate
from app.models.document import Document
from app.models.client import Client
from app.services.matching_engine import engine_instance

logger = structlog.get_logger()


class EntityDiscoveryConfig:
    """Configuration for entity discovery thresholds"""
    EXECUTIVE_CONFIDENCE_THRESHOLD = 0.75
    # Lowered from 3→2: realistic article volumes rarely produce 3 distinct docs per executive
    EXECUTIVE_MENTION_THRESHOLD = 2
    EXECUTIVE_MIN_DOCUMENTS = 2
    COMPETITOR_MENTION_THRESHOLD = 3
    # Lowered from 0.75→0.70: _calculate_org_confidence base is 0.70 for names without
    # corporate suffixes (Inc/Corp/Ltd). The old 0.75 threshold permanently blocked all
    # such candidates regardless of how many times they appeared.
    COMPETITOR_CONFIDENCE_THRESHOLD = 0.70
    COMPETITOR_MIN_DOCUMENTS = 2

    # Organizations to always ignore — media outlets, financial terminals, generic terms
    IGNORED_ORGANIZATIONS = {
        "microsoft", "google", "amazon", "linkedin", "reuters", "bloomberg",
        "msn", "businessline", "techcrunch", "moneycontrol.com", "ndtv",
        "the times of india", "hindustan times", "economic times", "et auto",
        "autocar", "autocar professional", "autocar india",
        "cardekho", "carlelo", "autopunditz", "motley fool", "seeking alpha",
        "barron", "barrons", "cnbc", "bbc", "cnn", "espn",
        "yahoo finance", "yahoo", "forbes", "wsj", "wall street journal",
        "business insider", "business standard", "value research",
        "infoworld", "thestreet", "marketwatch", "zacks", "benzinga",
        "the new stack", "mit technology review", "daily sabah",
        "sec", "ipo", "ai", "cpu", "gpu", "llm", "uco bank",
        "super", "rgb", "yoy", "bee", "cev", "ev", "cto", "cfo",
        "pr newswire", "globe newswire", "businesswire", "pr",
        "softbank", "infosys", "tcs", "wipro",
        # Financial data / tech media platforms
        "marketbeat", "cleantechnica", "electrek", "the verge", "wired",
        "techradar", "venturebeat", "engadget", "gizmodo", "mashable",
        "ars technica", "arstechnica", "9to5mac", "9to5google",
        "statistics indexbox", "indexbox", "statista",
    }

    # Name suffixes that indicate media/analytics entities when appended to a root word
    MEDIA_COMPOUND_SUFFIXES = {"beat", "technica", "watch", "wire", "hub", "box"}

    # Maximum length for person names
    MAX_PERSON_NAME_LENGTH = 100


class EntityDiscoveryEngine:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            self.nlp = None

    def extract_ner_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract PERSON and ORG entities using spaCy NER"""
        if not self.nlp:
            return []
        
        doc = self.nlp(text)
        extracted = []
        for ent in doc.ents:
            if ent.label_ in ["PERSON", "ORG"]:
                extracted.append({
                    "name": ent.text.strip(),
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char
                })
        return extracted

    def process_document(
        self,
        db: Session,
        document_id: str,
        client_id: str
    ) -> Dict[str, Any]:
        """
        Process a document for intelligent entity discovery.
        
        Pipeline:
        Document -> NER Extraction -> Known Entity Check -> Create Candidate if Unknown
        """
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document or not document.normalized_content:
            return {"status": "skipped", "reason": "No document content"}
        
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return {"status": "error", "reason": "Client not found"}
        
        # Extract entities using NER
        ner_entities = self.extract_ner_entities(document.normalized_content)
        
        if not ner_entities:
            return {"status": "skipped", "reason": "No NER entities found"}
        
        results = {
            "executive_candidates_created": 0,
            "competitor_candidates_created": 0,
            "executive_candidates_updated": 0,
            "competitor_candidates_updated": 0,
            "existing_executives_matched": 0,
            "existing_competitors_matched": 0
        }
        
        # Get client's brand entity for filtering
        client_brand = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "brand"
        ).first()
        
        # Process each extracted entity
        for entity_data in ner_entities:
            entity_name = entity_data["name"]
            entity_label = entity_data["label"]
            
            if entity_label == "PERSON":
                result = self._process_person_entity(
                    db, client_id, entity_name, document_id
                )
                if result == "candidate_created":
                    results["executive_candidates_created"] += 1
                elif result == "candidate_updated":
                    results["executive_candidates_updated"] += 1
                elif result == "existing_matched":
                    results["existing_executives_matched"] += 1
                    
            elif entity_label == "ORG":
                result = self._process_org_entity(
                    db, client_id, entity_name, document_id, client_brand
                )
                if result == "candidate_created":
                    results["competitor_candidates_created"] += 1
                elif result == "candidate_updated":
                    results["competitor_candidates_updated"] += 1
                elif result == "existing_matched":
                    results["existing_competitors_matched"] += 1
        
        db.commit()
        return {"status": "completed", **results}

    def _process_person_entity(
        self,
        db: Session,
        client_id: str,
        person_name: str,
        document_id: str
    ) -> str:
        """
        Process a PERSON entity:
        - Check if known executive exists
        - If not, create or update ExecutiveCandidate
        """
        # Normalize name for matching
        normalized_name = self._normalize_name(person_name)
        
        # Advisory lock for concurrency protection
        hash_str = f"{client_id}:{normalized_name}"
        hash_val = int(hashlib.md5(hash_str.encode()).hexdigest()[:15], 16) - 2**63
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": hash_val})
        
        # Smart match against verified executives (Part 2)
        verified_executives = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "person"
        ).all()
        
        matched_executive = None
        for exec_entity in verified_executives:
            # Check name match
            if self._normalize_name(exec_entity.name) == normalized_name:
                matched_executive = exec_entity
                break
            # Check aliases
            for alias in exec_entity.aliases:
                if self._normalize_name(alias.alias_text) == normalized_name:
                    matched_executive = exec_entity
                    break
            # Check last name / first name match if unique/specific
            exec_parts = [p.lower() for p in exec_entity.name.split()]
            cand_parts = [p.lower() for p in person_name.split()]
            if len(cand_parts) == 1 and cand_parts[0] in exec_parts:
                matched_executive = exec_entity
                break
                
        if matched_executive:
            # Create entity mention if not exists
            existing_mention = db.query(EntityMention).filter(
                EntityMention.document_id == document_id,
                EntityMention.entity_id == matched_executive.id
            ).first()
            
            if not existing_mention:
                mention = EntityMention(
                    document_id=document_id,
                    entity_id=matched_executive.id,
                    role="PERSON",
                    mention_count=1,
                    confidence_score=1.0
                )
                db.add(mention)
            else:
                existing_mention.mention_count += 1
            
            return "existing_matched"
        
        # Check if candidate already exists
        existing_candidate = db.query(ExecutiveCandidate).filter(
            ExecutiveCandidate.client_id == client_id,
            ExecutiveCandidate.name.ilike(normalized_name)
        ).first()
        
        if existing_candidate:
            # Update existing candidate only if this document is new to prevent duplicate mention increments
            if document_id not in existing_candidate.source_documents:
                existing_candidate.mention_count += 1
                updated_docs = list(existing_candidate.source_documents)
                updated_docs.append(document_id)
                existing_candidate.source_documents = updated_docs
                existing_candidate.last_seen = datetime.now(timezone.utc)
                # Recalculate confidence dynamically
                existing_candidate.confidence = self._calculate_person_confidence(
                    db,
                    client_id,
                    existing_candidate.name,
                    existing_candidate.source_documents,
                    existing_candidate.mention_count
                )
                logger.info(
                    "candidate_updated",
                    client_id=client_id,
                    candidate_name=existing_candidate.name,
                    candidate_type="executive",
                    mention_count=existing_candidate.mention_count,
                    confidence=existing_candidate.confidence,
                    document_ids=existing_candidate.source_documents
                )
            
            return "candidate_updated"
        
        # Layered validation of the candidate
        is_valid, reject_layer, reject_reason = self._is_valid_person_name_layered(person_name, db, client_id)
        if not is_valid:
            logger.info(
                "executive_candidate_rejected",
                candidate=person_name,
                reason=reject_reason,
                layer=reject_layer,
                confidence=0.0,
                mention_count=1,
                documents=[document_id]
            )
            return "skipped"
        
        confidence = self._calculate_person_confidence(db, client_id, person_name, [document_id], 1)
        
        # We save candidates regardless of confidence threshold, but filter them at promotion.
        # This keeps the candidate pool discoverable as requested.
        candidate = ExecutiveCandidate(
            client_id=client_id,
            name=person_name,
            mention_count=1,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            confidence=confidence,
            source_documents=[document_id]
        )
        db.add(candidate)
        db.flush()
        
        logger.info(
            "candidate_inserted",
            client_id=client_id,
            candidate_name=candidate.name,
            candidate_type="executive",
            mention_count=candidate.mention_count,
            confidence=candidate.confidence,
            document_ids=candidate.source_documents
        )
        return "candidate_created"

    def _process_org_entity(
        self,
        db: Session,
        client_id: str,
        org_name: str,
        document_id: str,
        client_brand: Optional[Entity]
    ) -> str:
        """
        Process an ORG entity:
        - Check if known competitor exists
        - If not and meets criteria, create or update CompetitorCandidate
        """
        normalized_name = self._normalize_name(org_name)
        org_name_lower = normalized_name.lower()
        
        # Advisory lock for concurrency protection
        hash_str = f"org:{client_id}:{org_name_lower}"
        hash_val = int(hashlib.md5(hash_str.encode()).hexdigest()[:15], 16) - 2**63
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": hash_val})
                # Skip if this is the client's own brand
        if client_brand and normalized_name == self._normalize_name(client_brand.name):
            return "skipped"
        
        # Skip ignored organizations unless they're in client's industry
        if normalized_name in EntityDiscoveryConfig.IGNORED_ORGANIZATIONS:
            if client_brand and client_brand.industry:
                return "skipped"
            return "skipped"
        
        # Get all client entities and match by normalized name in Python
        client_entities = db.query(Entity).filter(Entity.client_id == client_id).all()
        existing_entity = next((e for e in client_entities if self._normalize_name(e.name) == normalized_name), None)
        
        if existing_entity:
            # Create entity mention if not exists
            existing_mention = db.query(EntityMention).filter(
                EntityMention.document_id == document_id,
                EntityMention.entity_id == existing_entity.id
            ).first()
            
            if not existing_mention:
                mention = EntityMention(
                    document_id=document_id,
                    entity_id=existing_entity.id,
                    role="ORG",
                    mention_count=1,
                    confidence_score=1.0
                )
                db.add(mention)
            
            return "existing_matched"
        
        # Check if candidate already exists by matching normalized names in Python
        client_candidates = db.query(CompetitorCandidate).filter(
            CompetitorCandidate.client_id == client_id
        ).all()
        existing_candidate = next((c for c in client_candidates if self._normalize_name(c.organization_name) == normalized_name), None)
        if existing_candidate:
            # Update existing candidate idempotently
            if document_id not in existing_candidate.source_documents:
                existing_candidate.mention_count += 1
                updated_docs = list(existing_candidate.source_documents)
                updated_docs.append(document_id)
                existing_candidate.source_documents = updated_docs
                existing_candidate.last_seen = datetime.now(timezone.utc)
                
                logger.info(
                    "candidate_updated",
                    client_id=client_id,
                    candidate_name=existing_candidate.organization_name,
                    candidate_type="competitor",
                    mention_count=existing_candidate.mention_count,
                    confidence=existing_candidate.confidence,
                    document_ids=existing_candidate.source_documents
                )
            
            return "candidate_updated"
        
        # Create new candidate - we create candidates for all ORG entities
        # Promotion to verified competitor happens later based on thresholds
        confidence = self._calculate_org_confidence(org_name)
        
        candidate = CompetitorCandidate(
            client_id=client_id,
            organization_name=org_name,
            mention_count=1,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            confidence=confidence,
            source_documents=[document_id]
        )
        db.add(candidate)
        db.flush()
        
        logger.info(
            "candidate_inserted",
            client_id=client_id,
            candidate_name=candidate.organization_name,
            candidate_type="competitor",
            mention_count=candidate.mention_count,
            confidence=candidate.confidence,
            document_ids=candidate.source_documents
        )
        return "candidate_created"

    def _is_valid_person_name(self, name: str) -> bool:
        """
        Validate that a person name is not corrupted and matches a human name pattern.
        Rejects: URLs, HTML, encoded strings, action verbs, publishers, products, and invalid shapes.
        """
        if not name:
            return False
        
        # Check for URL fragments, URL encoded strings, HTML tags
        if re.search(r'^https?://', name) or re.search(r'%[0-9A-F]{2}', name) or re.search(r'<[^>]+>', name):
            return False
            
        # Check maximum/minimum length
        name_clean = name.strip()
        if len(name_clean) > EntityDiscoveryConfig.MAX_PERSON_NAME_LENGTH or len(name_clean) < 2:
            return False
            
        # Layer 2: Human Name Validation (2 to 4 parts)
        parts = [p for p in re.split(r'[\s,.-]+', name_clean) if p]
        if not (2 <= len(parts) <= 4):
            return False
            
        # Ensure parts start with uppercase (ignoring initials or particles)
        for p in parts:
            if p.isalpha() and not p[0].isupper():
                return False
                
        # Layer 3: Action Phrase Filter
        action_verbs = {
            "buy", "sell", "invest", "watch", "read", "see", "compare", "review", 
            "drive", "want", "learn", "get", "upgrade", "join", "stock", "earning", 
            "earnings", "dividend", "dividends", "price", "share", "shares", "target", 
            "rally", "drop", "plunge", "climb", "short", "news", "report", "update"
        }
        if any(p.lower() in action_verbs for p in parts):
            return False
            
        # Layer 4: Publisher / Organization Filter
        publishers = {
            "reuters", "bloomberg", "cnbc", "yahoo", "finance", "electrek", "marketwatch", 
            "barron", "insider", "forbes", "inc", "corp", "co", "news", "wall", "street", 
            "journal", "times", "post", "globe", "mail", "tv", "press", "media", "motley", 
            "fool", "alpha", "seeking", "zacks", "benzinga", "thestreet", "market", "wire", 
            "pr", "newswire"
        }
        if any(p.lower() in publishers for p in parts):
            return False
            
        # Layer 5: Product Filter
        products = {
            "tesla", "cybertruck", "roadster", "fsd", "autopilot", "optimus", "supercharger", 
            "megapack", "iphone", "ipad", "macbook", "pepsi", "coke", "coca-cola", "product", 
            "software", "hardware", "battery", "batteries", "charger", "chargers", "vehicle", 
            "vehicles", "automaker", "automakers", "car", "cars", "model"
        }
        if any(p.lower() in products for p in parts):
            return False
            
        return True

    def _is_valid_person_name_layered(self, name: str, db: Session, client_id: str) -> tuple[bool, str, str]:
        """
        Validate candidate name across 5 layers.
        Returns: (is_valid, validation_layer, reason)
        """
        if not name:
            return False, "Layer 2 — Human Name Validation", "Empty name"
            
        name_clean = name.strip()
        if len(name_clean) > EntityDiscoveryConfig.MAX_PERSON_NAME_LENGTH or len(name_clean) < 2:
            return False, "Layer 2 — Human Name Validation", f"Length {len(name_clean)} out of bounds"
            
        # Check for URL fragments, URL encoded strings, HTML tags
        if re.search(r'^https?://', name_clean) or re.search(r'%[0-9A-F]{2}', name_clean) or re.search(r'<[^>]+>', name_clean):
            return False, "Layer 2 — Human Name Validation", "Contains URL, HTML or URL encoding"
            
        # Split by whitespace/commas/periods/hyphens
        parts = [p.strip() for p in re.split(r'[\s,]+', name_clean) if p.strip()]
        if not (2 <= len(parts) <= 5):
            return False, "Layer 2 — Human Name Validation", f"Invalid name parts count: {len(parts)} (expected 2 to 5)"
            
        # Layer 1 — NER Validation: Cross-check against existing non-person entities or labels
        existing_non_person = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.name.ilike(name_clean),
            Entity.entity_type != "person"
        ).first()
        if existing_non_person:
            return False, "Layer 1 — NER Validation", f"Matches existing non-person entity of type: {existing_non_person.entity_type}"
            
        # Layer 2 — Human Name Validation Heuristics (tolerate middle initials, suffixes, hyphenated names)
        lowercase_particles = {"de", "del", "du", "la", "von", "van", "der", "di", "da"}
        valid_suffixes = {"jr", "jr.", "sr", "sr.", "iii", "iv", "v", "ii", "esq", "phd", "md"}
        
        for idx, part in enumerate(parts):
            part_clean = part.rstrip(".,")
            if not part_clean:
                continue
            
            subparts = part_clean.split("-")
            for sp in subparts:
                if not sp:
                    continue
                if sp.lower() in lowercase_particles and idx > 0 and idx < len(parts) - 1:
                    continue
                if sp.lower() in valid_suffixes and idx == len(parts) - 1:
                    continue
                if len(sp) == 1 and sp.isupper():
                    continue
                if sp[0].isalpha() and not sp[0].isupper():
                    return False, "Layer 2 — Human Name Validation", f"Part '{part}' is not capitalized"
                if not sp.replace("'", "").replace(".", "").replace("-", "").isalpha():
                    return False, "Layer 2 — Human Name Validation", f"Part '{part}' contains invalid characters"

        # Layer 3 — Action Phrase Filter
        action_verbs = {
            "buy", "sell", "invest", "watch", "read", "see", "compare", "review", 
            "drive", "want", "learn", "get", "upgrade", "join", "stock", "earning", 
            "earnings", "dividend", "dividends", "price", "share", "shares", "target", 
            "rally", "drop", "plunge", "climb", "short", "news", "report", "update"
        }
        if parts[0].lower().rstrip(".,") in action_verbs:
            return False, "Layer 3 — Action Phrase Filter", f"Starts with action/marketing verb: '{parts[0]}'"

        # Layer 4 — Publisher / Organization Filter
        publishers = {
            "reuters", "bloomberg", "cnbc", "yahoo", "finance", "electrek", "marketwatch", 
            "barron", "barrons", "fool", "motley", "forbes", "inc", "corp", "co", "news", "wall", "street", 
            "journal", "times", "post", "globe", "mail", "tv", "press", "media", "motley", 
            "fool", "alpha", "seeking", "zacks", "benzinga", "thestreet", "market", "wire", 
            "pr", "newswire"
        }
        for part in parts:
            p_lower = part.lower().rstrip(".,")
            if p_lower in publishers:
                return False, "Layer 4 — Publisher / Organization Filter", f"Matches publisher keyword: '{p_lower}'"

        # Layer 5 — Product Filter
        products = {
            "tesla", "cybertruck", "roadster", "fsd", "autopilot", "optimus", "supercharger", 
            "megapack", "iphone", "ipad", "macbook", "pepsi", "coke", "coca-cola", "product", 
            "software", "hardware", "battery", "batteries", "charger", "chargers", "vehicle", 
            "vehicles", "automaker", "automakers", "car", "cars", "model", "semi"
        }
        for part in parts:
            p_lower = part.lower().rstrip(".,")
            if p_lower in products:
                return False, "Layer 5 — Product Filter", f"Matches product/technology keyword: '{p_lower}'"

        return True, "", ""

    def _normalize_name(self, name: str) -> str:
        """Normalize entity name for matching, stripping corporate suffixes"""
        cleaned = name.strip().lower()
        cleaned = re.sub(r'[,.\s\-\/]+$', '', cleaned)
        
        # Regex to strip common corporate suffixes at the end of name
        pattern = r'\b(inc|corp|corporation|ltd|limited|llc|co|company|holdings|group)\b$'
        
        prev = ""
        while cleaned != prev:
            prev = cleaned
            cleaned = re.sub(pattern, '', cleaned).strip()
            cleaned = re.sub(r'[,.\s\-\/]+$', '', cleaned)
            
        return cleaned or name.strip().lower()

    def _has_executive_context(self, db: Session, name: str, doc_ids: List[str]) -> bool:
        """Helper to scan documents for executive context near the mention"""
        if not doc_ids:
            return False
        docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
        title_pattern = re.compile(r'\b(ceo|cfo|coo|executive|president|director|chairman|founder|vp|chief)\b', re.IGNORECASE)
        for doc in docs:
            if not doc.normalized_content:
                continue
            for match in re.finditer(re.escape(name), doc.normalized_content, re.IGNORECASE):
                start, end = match.start(), match.end()
                context_start = max(0, start - 100)
                context_end = min(len(doc.normalized_content), end + 100)
                context = doc.normalized_content[context_start:context_end]
                if title_pattern.search(context):
                    return True
        return False

    def _calculate_person_confidence(self, db: Session, client_id: str, person_name: str, doc_ids: List[str], mention_count: int) -> float:
        """Calculate confidence score combining NER, mentions, diversity, context, and aliases"""
        confidence = 0.50  # Base NER confidence
        
        parts = [p for p in re.split(r'[\s,.-]+', person_name.strip()) if p]
        
        # Standard format boost
        if len(parts) == 2:
            confidence += 0.10
            
        # Mention frequency boost: +0.05 per mention above 1, capped at 0.15
        confidence += min(0.15, (mention_count - 1) * 0.05)
        
        # Document diversity boost: +0.05 per document above 1, capped at 0.20
        doc_count = len(doc_ids)
        confidence += min(0.20, (doc_count - 1) * 0.05)
        
        # Context quality boost: +0.15 if title keywords appear nearby
        if self._has_executive_context(db, person_name, doc_ids):
            confidence += 0.15
            
        # Existing verified executive alias boost: +0.20
        verified_execs = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "person"
        ).all()
        for ve in verified_execs:
            ve_parts = ve.name.split()
            if len(ve_parts) >= 2 and len(parts) >= 2:
                if ve_parts[-1].lower() == parts[-1].lower():
                    confidence += 0.20
                    break
                    
        return min(1.0, confidence)

    def _calculate_org_confidence(self, org_name: str) -> float:
        """Calculate confidence score for an organization entity"""
        # Base confidence
        confidence = 0.70
        
        # Boost for organizations that look like company names
        if any(indicator in org_name.lower() for indicator in 
               ["inc", "corp", "ltd", "llc", "company", "corporation"]):
            confidence += 0.15
        
        return min(1.0, confidence)

    def _is_valid_org_name(self, org_name: str, client_name: str = "") -> bool:
        """
        Guard against promoting media outlets, news publishers, financial platforms,
        abbreviations, possessives, and client self-references as competitors.
        Returns True if the name looks like a real competitor company.
        """
        normalized = self._normalize_name(org_name)

        # Block anything in the expanded ignore list
        if normalized in EntityDiscoveryConfig.IGNORED_ORGANIZATIONS:
            return False

        # Block very short abbreviations (≤3 chars) — GPU, AI, EV, etc.
        if len(normalized) <= 3:
            return False

        # Block names that end with a domain TLD (.com, .co, .net, .org)
        if re.search(r'\.(com|co|net|org|io|in|uk)$', normalized):
            return False

        # Block possessives: "Tesla's", "PepsiCo's", "Elon Musk's"
        if org_name.rstrip().endswith(("'s", "’s", "s'")):
            return False

        # Block names that start with the client's own brand
        # e.g. client="Tata Motors" blocks "Tata Motors CV", "Tata Motors PV"
        # e.g. client="PepsiCo" blocks "PepsiCo CFO", "PepsiCo Q2 2026"
        if client_name:
            client_normalized = self._normalize_name(client_name).lower()
            org_normalized_lower = normalized.lower()
            # Block if the org name *starts with* the client brand (to catch sub-brands/departments)
            if client_normalized and org_normalized_lower.startswith(client_normalized):
                return False
            # Also block if the client brand appears verbatim as the first token
            client_first_token = client_normalized.split()[0] if client_normalized.split() else ""
            org_first_token = org_normalized_lower.split()[0] if org_normalized_lower.split() else ""
            # Only apply single-token rule when client name is a single word (e.g. "Tata", "Pepsi")
            if len(client_normalized.split()) == 1 and org_first_token == client_first_token:
                return False

        # Block names that contain common media/news/financial keywords
        media_keywords = {
            "times", "news", "post", "press", "media", "journal",
            "daily", "weekly", "magazine", "wire", "digest",
            "briefing", "insider", "watch", "report", "beat",
            "fool", "alpha", "seeking", "cramer", "street",
        }
        name_words = set(re.split(r'[\s,.-]+', normalized))
        if name_words & media_keywords:
            return False

        # Block names that look like financial/regulatory bodies
        financial_bodies = {
            "ntsb", "nhtsa", "sec", "fdic", "fed", "niti",
            "faa", "epa", "doe", "doj", "ftc",
        }
        if normalized in financial_bodies:
            return False

        # Block multi-word names that look like headlines or sentences (>4 words)
        if len(org_name.split()) > 4:
            return False

        return True

    def promote_competitor_candidates(
        self,
        db: Session,
        client_id: str
    ) -> Dict[str, Any]:
        """
        Promote competitor candidates to verified competitors based on rules:
        - minimum_mentions reached
        - confidence threshold reached
        - appears in multiple independent documents
        - passes org name validity check (filters media outlets, abbreviations, etc.)
        """
        candidates = db.query(CompetitorCandidate).filter(
            CompetitorCandidate.client_id == client_id,
            CompetitorCandidate.promoted_to_competitor_id.is_(None)
        ).all()

        promoted_count = 0

        # Fetch client for brand name (needed for self-reference check)
        client = db.query(Client).filter(Client.id == client_id).first()

        for candidate in candidates:
            # Gate: must look like a real company, not a news source or abbreviation
            if not self._is_valid_org_name(candidate.organization_name, client_name=client.name if client else ""):
                logger.info(
                    "competitor_candidate_rejected",
                    client_id=client_id,
                    candidate_name=candidate.organization_name,
                    reason="Failed org name validity check (media outlet, abbreviation, self-reference, or headline)"
                )
                continue

            # Check promotion criteria
            meets_mention_threshold = candidate.mention_count >= EntityDiscoveryConfig.COMPETITOR_MENTION_THRESHOLD
            meets_confidence_threshold = candidate.confidence >= EntityDiscoveryConfig.COMPETITOR_CONFIDENCE_THRESHOLD
            meets_document_threshold = len(candidate.source_documents) >= EntityDiscoveryConfig.COMPETITOR_MIN_DOCUMENTS

            if meets_mention_threshold and meets_confidence_threshold and meets_document_threshold:
                # Check if entity already exists by matching normalized names in Python
                normalized_cand_name = self._normalize_name(candidate.organization_name)
                client_entities = db.query(Entity).filter(Entity.client_id == client_id).all()
                existing_entity = next((e for e in client_entities if self._normalize_name(e.name) == normalized_cand_name), None)
                
                if not existing_entity:
                    # Create new competitor entity
                    new_entity = Entity(
                        client_id=client_id,
                        name=candidate.organization_name,
                        entity_type="competitor"
                    )
                    db.add(new_entity)
                    db.flush()  # Get the ID
                    
                    new_keyword = EntityKeyword(
                        entity_id=new_entity.id,
                        keyword_text=candidate.organization_name,
                        match_type="exact",
                        category="PRIMARY",
                        priority=1,
                        is_active=True
                    )
                    db.add(new_keyword)
                    
                    # Mark candidate as promoted
                    candidate.promoted_to_competitor_id = new_entity.id
                    candidate.promoted_at = datetime.now(timezone.utc)
                    
                    logger.info(
                        "candidate_promoted",
                        client_id=client_id,
                        candidate_name=candidate.organization_name,
                        candidate_type="competitor",
                        new_entity_id=str(new_entity.id),
                        mention_count=candidate.mention_count
                    )
                    
                    promoted_count += 1
        
        db.commit()
        
        if promoted_count > 0:
            engine_instance.refresh_processor(db)
        
        # Trigger benchmark calculation for newly promoted competitors
        if promoted_count > 0:
            from app.services.intelligence.benchmark_engine import BenchmarkEngine
            benchmark_engine = BenchmarkEngine()
            try:
                benchmark_engine.calculate_competitor_benchmarks(db, client_id)
            except Exception as e:
                logger.error(
                    "competitor_benchmark_calculation_failed_after_promotion",
                    client_id=client_id,
                    error=str(e)
                )
                
        return {"promoted_count": promoted_count}

    def promote_executive_candidates(
        self,
        db: Session,
        client_id: str
    ) -> Dict[str, Any]:
        """
        Promote executive candidates to verified executives based on rules:
        - Passed all validation layers (NER, human name, verbs, publishers, products)
        - Mentioned in at least 3 different documents
        - Confidence >= 75%
        - Not already present as an entity
        """
        candidates = db.query(ExecutiveCandidate).filter(
            ExecutiveCandidate.client_id == client_id,
            ExecutiveCandidate.promoted_to_executive_id.is_(None)
        ).all()
        
        promoted_count = 0
        promoted_executives = []
        
        for candidate in candidates:
            # 1. Validation Layers check
            is_valid, reject_layer, reject_reason = self._is_valid_person_name_layered(candidate.name, db, client_id)
            if not is_valid:
                logger.info(
                    "executive_candidate_rejected",
                    candidate=candidate.name,
                    reason=reject_reason,
                    layer=reject_layer,
                    confidence=candidate.confidence,
                    mention_count=candidate.mention_count,
                    documents=candidate.source_documents
                )
                continue

            # 2. Threshold checks
            meets_mention_threshold = candidate.mention_count >= EntityDiscoveryConfig.EXECUTIVE_MENTION_THRESHOLD
            meets_confidence_threshold = candidate.confidence >= EntityDiscoveryConfig.EXECUTIVE_CONFIDENCE_THRESHOLD
            meets_document_threshold = len(candidate.source_documents) >= EntityDiscoveryConfig.EXECUTIVE_MIN_DOCUMENTS
            
            if not (meets_mention_threshold and meets_confidence_threshold and meets_document_threshold):
                reasons = []
                if not meets_mention_threshold:
                    reasons.append(f"mentions {candidate.mention_count} < {EntityDiscoveryConfig.EXECUTIVE_MENTION_THRESHOLD}")
                if not meets_document_threshold:
                    reasons.append(f"documents {len(candidate.source_documents)} < {EntityDiscoveryConfig.EXECUTIVE_MIN_DOCUMENTS}")
                if not meets_confidence_threshold:
                    reasons.append(f"confidence {candidate.confidence:.2f} < {EntityDiscoveryConfig.EXECUTIVE_CONFIDENCE_THRESHOLD:.2f}")
                
                logger.info(
                    "executive_candidate_rejected",
                    candidate=candidate.name,
                    reason="; ".join(reasons),
                    layer="Layer 7 — Evidence Requirement",
                    confidence=candidate.confidence,
                    mention_count=candidate.mention_count,
                    documents=candidate.source_documents
                )
                continue

            # Check if entity already exists
            existing_entity = db.query(Entity).filter(
                Entity.client_id == client_id,
                Entity.name.ilike(candidate.name),
                Entity.entity_type == "person"
            ).first()
            
            if not existing_entity:
                # Create new executive entity
                new_entity = Entity(
                    client_id=client_id,
                    name=candidate.name,
                    entity_type="person"
                )
                db.add(new_entity)
                db.flush()  # Get the ID
                
                new_keyword = EntityKeyword(
                    entity_id=new_entity.id,
                    keyword_text=candidate.name,
                    match_type="exact",
                    category="PRIMARY",
                    priority=1,
                    is_active=True
                )
                db.add(new_keyword)
                
                # Mark candidate as promoted
                candidate.promoted_to_executive_id = new_entity.id
                candidate.promoted_at = datetime.now(timezone.utc)
                
                logger.info(
                    "executive_promoted",
                    candidate=candidate.name,
                    final_confidence=candidate.confidence,
                    validation_results="passed all layers",
                    reason_promoted=f"Met thresholds: mentions {candidate.mention_count} >= {EntityDiscoveryConfig.EXECUTIVE_MENTION_THRESHOLD}, docs {len(candidate.source_documents)} >= {EntityDiscoveryConfig.EXECUTIVE_MIN_DOCUMENTS}, confidence {candidate.confidence:.2f} >= {EntityDiscoveryConfig.EXECUTIVE_CONFIDENCE_THRESHOLD:.2f}"
                )
                
                promoted_count += 1
                promoted_executives.append({
                    "name": candidate.name,
                    "entity_id": str(new_entity.id),
                    "mention_count": candidate.mention_count,
                    "confidence": candidate.confidence
                })
            else:
                # Link candidate to existing
                candidate.promoted_to_executive_id = existing_entity.id
                candidate.promoted_at = datetime.now(timezone.utc)
                logger.info(
                    "executive_promoted",
                    candidate=candidate.name,
                    final_confidence=candidate.confidence,
                    validation_results="passed all layers (matched existing)",
                    reason_promoted="Already present as verified executive entity"
                )
        
        db.commit()
        
        if promoted_count > 0:
            engine_instance.refresh_processor(db)
        
        # Trigger executive reputation calculation for newly promoted executives
        if promoted_executives:
            from app.services.intelligence.executive_reputation_engine import ExecutiveReputationEngine
            reputation_engine = ExecutiveReputationEngine()
            try:
                reputation_engine.calculate_executive_reputation(db, client_id)
            except Exception as e:
                logger.error(
                    "executive_reputation_calculation_failed_after_promotion",
                    client_id=client_id,
                    error=str(e)
                )
        
        return {
            "promoted_count": promoted_count,
            "promoted_executives": promoted_executives
        }


# Global instance
entity_discovery_engine = EntityDiscoveryEngine()
