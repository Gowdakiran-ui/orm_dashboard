import time
import re
from sqlalchemy.orm import Session
from flashtext import KeywordProcessor
from app.models.entity import EntityKeyword, Entity, EntityAlias
from app.models.document import DocumentMatch
from app.models.metrics import MatchingMetrics
from typing import Dict, Any, List, Optional, Set

def get_client_boost_terms(db: Session, client_id) -> Dict[str, Set[str]]:
    """
    M6-F1: per-client executive/product terms for evaluate_match_accuracy's
    boost logic, sourced from the same data model entity_discovery.py already
    reads for the equivalent product-blocklist problem (see its "HONEST
    LIMITATION" comment there) instead of a hardcoded tesla/meta/tata dict.

    Executives are real Entity(entity_type="person") rows for this client
    (as executive_reputation_engine.py already relies on) plus their
    name/alias/EXECUTIVE-keyword text. Products are Entity(entity_type=
    "product") rows plus PRODUCT-category keywords -- honestly inert for any
    client that hasn't had product entities populated yet, same limitation
    entity_discovery.py already documents, not a new one introduced here.
    """
    executive_terms: Set[str] = set()
    person_entities = db.query(Entity).filter(
        Entity.client_id == client_id,
        Entity.entity_type == "person"
    ).all()
    for p in person_entities:
        if p.name:
            executive_terms.add(p.name.lower())
        for alias in p.aliases:
            if alias.alias_text:
                executive_terms.add(alias.alias_text.lower())

    exec_keywords = db.query(EntityKeyword).join(Entity, Entity.id == EntityKeyword.entity_id).filter(
        Entity.client_id == client_id,
        EntityKeyword.category == "EXECUTIVE",
        EntityKeyword.is_active == True
    ).all()
    for kw in exec_keywords:
        if kw.keyword_text:
            executive_terms.add(kw.keyword_text.lower())

    product_terms: Set[str] = set()
    product_entities = db.query(Entity).filter(
        Entity.client_id == client_id,
        Entity.entity_type == "product"
    ).all()
    for prod in product_entities:
        if prod.name:
            product_terms.add(prod.name.lower())
        for alias in prod.aliases:
            if alias.alias_text:
                product_terms.add(alias.alias_text.lower())

    product_keywords = db.query(EntityKeyword).join(Entity, Entity.id == EntityKeyword.entity_id).filter(
        Entity.client_id == client_id,
        EntityKeyword.category == "PRODUCT",
        EntityKeyword.is_active == True
    ).all()
    for kw in product_keywords:
        if kw.keyword_text:
            product_terms.add(kw.keyword_text.lower())

    return {"executive_terms": executive_terms, "product_terms": product_terms}

class MatchingEngineConfig:
    """
    Configuration for the matching engine accuracy scoring.
    """
    context_window_size: int = 150
    confidence_threshold: float = 0.60
    ambiguity_delta: float = 0.15

class GlobalMatchingEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            import threading
            cls._instance = super(GlobalMatchingEngine, cls).__new__(cls)
            cls._instance.processor = KeywordProcessor(case_sensitive=False)
            cls._instance.is_loaded = False
            cls._instance.config = MatchingEngineConfig()
            cls._instance.lock = threading.Lock()
        return cls._instance

    def refresh_processor(self, db: Session):
        """
        Rebuild the global processor with all active keywords.
        Supports hot reloading without restarting the application.
        """
        with self.lock:
            start_time = time.time()
            
            # We need a new processor to avoid downtime during rebuild, then swap
            new_processor = KeywordProcessor(case_sensitive=False)
            
            active_keywords = db.query(EntityKeyword).join(Entity).filter(EntityKeyword.is_active == True).all()
            
            for kw in active_keywords:
                # We encode metadata into the clean_name of FlashText
                # Format: client_id|entity_id|match_type|priority|category|keyword_text
                # W1: We also append the raw keyword text to reconstruct exactly what matched
                metadata_str = f"{kw.entity.client_id}|{kw.entity_id}|{kw.match_type}|{kw.priority}|{kw.category}|{kw.keyword_text}"
                new_processor.add_keyword(kw.keyword_text, metadata_str)
                
            self.processor = new_processor
            self.is_loaded = True
            
            print(f"GlobalMatchingEngine: Refreshed with {len(active_keywords)} keywords in {time.time() - start_time:.4f}s")
            return len(active_keywords)

    def normalize_executive_titles(self, text: str) -> str:
        """
        Normalize executive titles case-insensitively in document text to improve matching robustness.
        E.g. "Managing Director & CEO" -> "CEO", "Co-Founder" -> "FOUNDER"
        """
        if not text:
            return ""
        # Managing Director & CEO / Chief Executive Officer -> CEO
        text = re.sub(r'\b(?:managing\s+director\s+&\s+)?chief\s+executive\s+officer\b', 'CEO', text, flags=re.IGNORECASE)
        text = re.sub(r'\bmanaging\s+director\s+and\s+ceo\b', 'CEO', text, flags=re.IGNORECASE)
        text = re.sub(r'\bmanaging\s+director\b', 'MD', text, flags=re.IGNORECASE)
        # Chief Technology Officer -> CTO
        text = re.sub(r'\bchief\s+technology\s+officer\b', 'CTO', text, flags=re.IGNORECASE)
        # Chief Operating Officer -> COO
        text = re.sub(r'\bchief\s+operating\s+officer\b', 'COO', text, flags=re.IGNORECASE)
        # Co-Founder / Co Founder -> FOUNDER
        text = re.sub(r'\bco[- ]founder\b', 'FOUNDER', text, flags=re.IGNORECASE)
        return text

    def find_matches(self, text: str) -> List[Dict[str, Any]]:
        """
        Find matches in text and decode metadata.
        Uses span_info=True from FlashText to support context extraction.
        """
        # Take local references to ensure thread safety against hot-swapping
        is_loaded = self.is_loaded
        processor = self.processor
        
        if not is_loaded or processor is None:
            raise RuntimeError("GlobalMatchingEngine is not loaded. Call refresh_processor first.")
            
        if not text:
            return []

        # 1. Normalize executive titles in text
        normalized_text = self.normalize_executive_titles(text)

        # 2. Extract keywords with span positions
        raw_matches_with_spans = processor.extract_keywords(normalized_text, span_info=True)
        
        parsed_matches = []
        for match_meta, start_idx, end_idx in raw_matches_with_spans:
            parts = match_meta.split('|')
            client_id, entity_id, match_type, priority, category = parts[0], parts[1], parts[2], parts[3], parts[4]
            # Handle if keyword_text was appended (pre-existing vs new format)
            matched_keyword = parts[5] if len(parts) > 5 else normalized_text[start_idx:end_idx]

            parsed_matches.append({
                "client_id": client_id,
                "entity_id": entity_id,
                "match_type": match_type,
                "priority": int(priority),
                "category": category,
                "matched_keyword": matched_keyword,
                "start_idx": start_idx,
                "end_idx": end_idx,
                "confidence": 1.0  # Default, will be refined in accuracy pass
            })
            
        return parsed_matches

    def evaluate_match_accuracy(
        self,
        doc_text: str,
        match: Dict[str, Any],
        entity_domain: Optional[str] = None,
        entity_name: Optional[str] = None,
        executive_terms: Optional[Set[str]] = None,
        product_terms: Optional[Set[str]] = None,
        entity_industry: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Performs context proximity & evidence accumulator logic for a single match.
        Returns an explainability metadata dictionary and the final confidence score.
        """
        start_idx = match["start_idx"]
        end_idx = match["end_idx"]
        category = match["category"]
        matched_keyword = match["matched_keyword"]
        priority = match["priority"]
        
        # 1. Extract context window
        half_window = self.config.context_window_size // 2
        window_start = max(0, start_idx - half_window)
        window_end = min(len(doc_text), end_idx + half_window)
        context_window = doc_text[window_start:window_end].lower()

        # 2. Initialize confidence score and audit trail
        # Base confidence starts high for primary name/strong aliases, medium for generic but exact match on main name, low for common abbreviations
        kw_lower = matched_keyword.lower()
        entity_name_lower = (entity_name or "").lower()
        
        # "tesla"/"meta"/"tata" already get dedicated negative-context
        # disambiguation at step 8 below (Nikola Tesla / tesla coil,
        # meta-analysis, unrelated Tata Group companies) -- stacking the
        # generic-alias penalty on top of that is redundant double scrutiny,
        # and live data confirmed it was the actual cause of a 54.7%
        # false-negative rejection rate on Tesla's own PRIMARY brand keyword
        # (see FINDINGS.md). Real short/ambiguous keywords with no dedicated
        # rule (tickers, acronyms) keep the existing generic-alias caution.
        DISAMBIGUATED_BY_NEGATIVE_CONTEXT_RULE = {"tesla", "meta", "tata"}
        is_generic_or_abbrev = kw_lower not in DISAMBIGUATED_BY_NEGATIVE_CONTEXT_RULE and (
            len(matched_keyword) <= 4 or kw_lower in {"fsd", "tsla"}
        )
        
        if category == "PRIMARY":
            base_confidence = 0.85
        elif kw_lower == entity_name_lower:
            # If it matches the company's primary name exactly (e.g. "Tesla" matching "Tesla")
            base_confidence = 0.75
        elif not is_generic_or_abbrev:
            base_confidence = 0.70
        else:
            base_confidence = 0.40

        confidence = base_confidence
        bonuses = []
        penalties = []
        rejection_reasons = []

        # 3. Apply Domain Match Boost (+0.25)
        # If client website/domain is mentioned anywhere in the document
        doc_text_lower = doc_text.lower()
        if entity_domain and entity_domain.lower() in doc_text_lower:
            confidence += 0.25
            bonuses.append({"type": "domain_match_boost", "value": 0.25, "reason": f"Entity domain '{entity_domain}' found in document"})

        entity_key = (entity_name or "").lower()

        # 4. Apply Executive Match Boost (+0.20)
        # M6-F1: generalized from a tesla/meta/tata-only hardcoded dict to
        # whichever executives are actually tracked (real person entities +
        # EXECUTIVE-category keywords) for this entity's client -- see
        # get_client_boost_terms above.
        found_executive = False
        if executive_terms:
            matched_exec_term = next((t for t in executive_terms if t in doc_text_lower), None)
            if matched_exec_term:
                confidence += 0.20
                bonuses.append({"type": "executive_match_boost", "value": 0.20, "reason": f"Executive mention found in document ('{matched_exec_term}')"})
                found_executive = True

        # 5. Apply Product Match Boost (+0.20)
        # M6-F1: generalized the same way -- product entities + PRODUCT
        # keywords for this entity's client, instead of a tesla/meta/tata-only
        # hardcoded dict.
        found_product = False
        if product_terms:
            matched_product_term = next((t for t in product_terms if t in doc_text_lower), None)
            if matched_product_term:
                confidence += 0.20
                bonuses.append({"type": "product_match_boost", "value": 0.20, "reason": f"Product or technology mention found in document ('{matched_product_term}')"})
                found_product = True

        # 6. Apply Industry Match Boost (+0.10)
        # M6-F1: uses this entity's own Entity.industry field (set at client
        # onboarding) instead of a hardcoded tesla/meta/tata term list. Weaker
        # signal than a curated multi-term list -- a single industry label --
        # but it is the per-client industry data that actually exists today.
        if entity_industry and entity_industry.lower() in doc_text_lower:
            confidence += 0.10
            bonuses.append({"type": "industry_match_boost", "value": 0.10, "reason": f"Industry context term '{entity_industry}' found in document"})

        # 7. Nearby Context Boost (+0.15)
        # General positive business indicators like company, corporation, stock, shares, ticker symbol, etc.
        positive_context_indicators = ["company", "corp", "inc", "ltd", "stock", "shares", "nasdaq", "nyse", "quarter", "revenue", "earnings"]
        if any(indicator in doc_text_lower for indicator in positive_context_indicators):
            confidence += 0.15
            bonuses.append({"type": "nearby_context_boost", "value": 0.15, "reason": "Business context indicators found in document"})

        # 8. Negative Context Penalty (-0.50)
        # E.g., "Nikola Tesla" in non-EV context, "meta-analysis" for Meta, "tata" in unrelated language or contexts
        has_negative_context = False
        if "tesla" in entity_key:
            if "nikola tesla" in doc_text_lower and not any(ev_kw in doc_text_lower for ev_kw in ["ev", "car", "motor", "battery", "stock", "musk", "factory"]):
                confidence -= 0.50
                penalties.append({"type": "negative_context_penalty", "value": -0.50, "reason": "Found 'Nikola Tesla' without automotive context"})
                has_negative_context = True
            elif "tesla coil" in doc_text_lower or "tesla's inventions" in doc_text_lower:
                confidence -= 0.50
                penalties.append({"type": "negative_context_penalty", "value": -0.50, "reason": "Found physical/historical Tesla context (tesla coil/invention)"})
                has_negative_context = True
        
        if "meta" in entity_key:
            # Common dictionary/prefix usage of "meta" (e.g. meta-analysis, metadata, meta-programming)
            meta_patterns = [r'\bmeta-analysis\b', r'\bmetadata\b', r'\bmeta-description\b', r'\bmeta-programming\b', r'\bmeta tag\b', r'\bmeta-review\b']
            if any(re.search(pat, doc_text_lower) for pat in meta_patterns):
                confidence -= 0.50
                penalties.append({"type": "negative_context_penalty", "value": -0.50, "reason": "Found prefix/generic linguistic usage of 'meta' (e.g. metadata, meta-analysis)"})
                has_negative_context = True

        if "tata" in entity_key:
            # E.g., "tata power", "tata consultancy", "tata steel" when matching "Tata Motors" specifically,
            # unless automotive keywords are present in the text
            other_tata_companies = ["consultancy", "tcs", "steel", "power", "communications", "chemicals", "capital", "tea", "starbucks", "elxsi", "sky"]
            if any(company in doc_text_lower for company in other_tata_companies):
                if not any(auto_kw in doc_text_lower for auto_kw in ["motor", "car", "ev", "harrier", "altroz", "nexon", "safari", "vehicle"]):
                    confidence -= 0.50
                    penalties.append({"type": "negative_context_penalty", "value": -0.50, "reason": "Found unrelated Tata Group company (e.g. TCS, Steel, Power) without automotive context"})
                    has_negative_context = True

        # 9. Risky Alias Penalty (-0.30)
        # If it's a generic alias and no positive context was found in the document
        if is_generic_or_abbrev and not (found_executive or found_product or (entity_domain and entity_domain.lower() in doc_text_lower)):
            confidence -= 0.30
            penalties.append({"type": "risky_alias_penalty", "value": -0.30, "reason": "Generic or short alias matched without supporting executive or product context"})

        # 10. Bound confidence between 0.0 and 1.0
        confidence = max(0.0, min(1.0, confidence))
        confidence = round(confidence, 2)

        # 11. Evaluate status
        status = "accepted"
        if confidence < self.config.confidence_threshold:
            status = "rejected"
            rejection_reasons.append(f"Confidence score {confidence} is below the threshold of {self.config.confidence_threshold}")

        metadata = {
            "status": status,
            "matched_keyword": matched_keyword,
            "base_confidence": base_confidence,
            "final_confidence": confidence,
            "bonuses": bonuses,
            "penalties": penalties,
            "rejection_reasons": rejection_reasons,
            "decision_history": [{
                "timestamp": time.time(),
                "action": "score_evaluation",
                "status": status,
                "confidence": confidence
            }]
        }

        return metadata

    def process_document(self, db: Session, document_id: str, text: str):
        """
        Process a document, save matches, and record metrics.
        Legacy method kept for compatibility.
        """
        start_time = time.time()
        matches = self.find_matches(text)
        
        unique_entities = set()
        db_matches = []
        for m in matches:
            if m["entity_id"] not in unique_entities:
                unique_entities.add(m["entity_id"])
                db_matches.append(DocumentMatch(
                    document_id=document_id,
                    matched_entity_id=m["entity_id"],
                    match_type=m["match_type"],
                    match_confidence=m["confidence"],
                    matched_text=m.get("matched_keyword", "[Hidden/Aggregated]")
                ))
                
        if db_matches:
            db.add_all(db_matches)
            
        processing_time = time.time() - start_time
        
        from app.utils.redis_client import redis_client
        redis_client.incrby('metrics:documents_processed', 1)
        redis_client.incrby('metrics:matches_found', len(unique_entities))
        redis_client.incrbyfloat('metrics:processing_time_total', processing_time)
        redis_client.set('metrics:keywords_loaded', len(self.processor))
        
        return db_matches

engine_instance = GlobalMatchingEngine()
