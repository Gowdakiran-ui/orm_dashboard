import spacy
import uuid
import structlog
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, text
from sqlalchemy.exc import IntegrityError
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

    # ── Ignore lists ────────────────────────────────────────────────────────
    # Split into two sets (A1.5). The original single IGNORED_ORGANIZATIONS
    # conflated two unrelated things: publishers/generic industry terms (which
    # are genuinely never a competitor) and real operating companies (which are
    # frequently *exactly* the competitor we want to discover). Keeping them in
    # one set is why `microsoft`/`google`/`amazon` were permanently unpromotable
    # for any client — confirmed live: Apple Inc has zero real competitors and
    # `microsoft` never even reaches CompetitorCandidate, because
    # _process_org_entity() skips on this same set.
    #
    # MEDIA_AND_GENERIC_TERMS — publishers, financial terminals, data platforms,
    # bare industry buzzwords and role acronyms. Never a competitor, for anyone.
    MEDIA_AND_GENERIC_TERMS = {
        "linkedin", "reuters", "bloomberg",
        "msn", "businessline", "techcrunch", "moneycontrol.com", "ndtv",
        "the times of india", "hindustan times", "economic times", "et auto",
        "autocar", "autocar professional", "autocar india",
        "cardekho", "carlelo", "autopunditz", "motley fool", "seeking alpha",
        "barron", "barrons", "cnbc", "bbc", "cnn", "espn",
        "yahoo finance", "yahoo", "forbes", "wsj", "wall street journal",
        "business insider", "business standard", "value research",
        "infoworld", "thestreet", "marketwatch", "zacks", "benzinga",
        "the new stack", "mit technology review", "daily sabah",
        "sec", "ipo", "ai", "cpu", "gpu", "llm",
        "super", "rgb", "yoy", "bee", "cev", "ev", "cto", "cfo", "coo",
        # A1.8 — same shape as the acronyms above (bare financial-report
        # terminology, never a competitor). "eps" (Earnings Per Share) was
        # the specific gap that let PepsiCo's junk "EPS" competitor through
        # (TASK_FORENSICS...md Phase 2 / TASK.md Phase 1); "ebitda"/"roi"/
        # "qoq" are the same class, added together per the same audit
        # rather than patched one at a time. Checked against all 84 live
        # entity names first — none collide.
        "eps", "ebitda", "roi", "qoq",
        "pr newswire", "globe newswire", "businesswire", "pr",
        # Financial data / tech media platforms
        "marketbeat", "cleantechnica", "electrek", "the verge", "wired",
        "techradar", "venturebeat", "engadget", "gizmodo", "mashable",
        "ars technica", "arstechnica", "9to5mac", "9to5google",
        "statistics indexbox", "indexbox", "statista",
        "gurufocus", "britannica money", "britannica",
        # A1.9 — known compound junk words Layer O4's whole-word split
        # misses ("newsroom" is one token, not "news"+"room", so it never
        # intersects media_keywords). Investigated a generic substring/
        # startswith check on media_keywords instead of a literal add, and
        # rejected it: it would also flag real names that merely start with
        # a keyword's letters by coincidence (e.g. a person or company
        # named "Newsom" would match "news" as a prefix) — a real
        # collision risk, not a hypothetical one, for a platform-wide,
        # permanent classifier. An exact-match addition here has zero such
        # risk and fixes the one confirmed case; add further compound
        # words the same way if more are found, rather than switching to
        # substring matching.
        "newsroom",
    }

    # REAL_COMPANY_DENYLIST — operating companies that were on the original
    # ignore list. They are NOT filtered out of competitor discovery any more.
    # Retained as a named set purely so IGNORED_ORGANIZATIONS below stays
    # byte-for-byte equivalent to what the executive-discovery Layer 6 filter
    # and _is_valid_person_name() have always seen — those two consumers are
    # deliberately unchanged by this phase.
    REAL_COMPANY_DENYLIST = {
        "microsoft", "google", "amazon", "uco bank",
        "softbank", "infosys", "tcs", "wipro",
    }

    # Preserved for existing consumers (executive Layer 6 / _is_valid_person_name /
    # _process_org_entity's person-side expectations). Identical membership to the
    # pre-split list — do not narrow this without re-auditing the executive path.
    IGNORED_ORGANIZATIONS = MEDIA_AND_GENERIC_TERMS | REAL_COMPANY_DENYLIST

    # Market-instrument / venue noise. "AAPL Shares", "NASDAQ", "Nifty 50" are
    # ORG-tagged by spaCy but are tickers, exchanges and index names, never
    # competitors. Split from the regulator set that already existed.
    MARKET_NOISE_TERMS = {
        "shares", "share", "stock", "stocks", "ticker", "index", "indices",
        "etf", "etfs", "adr", "futures", "options", "dividend", "dividends",
        "earnings", "premarket", "aftermarket", "holdings",
    }

    EXCHANGES_AND_REGULATORS = {
        "nasdaq", "nyse", "amex", "dow jones", "dow", "s&p", "sp500",
        "ftse", "nikkei", "hang seng", "nifty", "sensex", "bse", "nse", "sebi",
        "ntsb", "nhtsa", "sec", "fdic", "fed", "niti",
        "faa", "epa", "doe", "doj", "ftc",
    }

    # Name suffixes that indicate media/analytics entities when appended to a root word
    MEDIA_COMPOUND_SUFFIXES = {"beat", "technica", "watch", "wire", "hub", "box"}

    # Near-duplicate guard for competitor promotion (A1.7), mirroring
    # EXECUTIVE_NAME_SIMILARITY_THRESHOLD. Set higher (0.88 vs 0.93 is *not*
    # comparable across name shapes — org names are shorter, so ratios run hot).
    # Verified against all 26 live promoted competitor names: the highest ratio
    # between any two genuinely-distinct names is < 0.70, so 0.88 has a wide
    # margin. Real near-dupes it catches: "General Motors"/"General Motor" 0.963,
    # "Mercedes-Benz"/"Mercedes Benz" 0.923, "Ford"/"Fords" 0.889.
    # Only applied to normalized names of >= 5 chars, because SequenceMatcher is
    # unstable on very short strings ("BYD"/"BYDs" 0.857, "Meta"/"Beta" 0.75) —
    # deliberately conservative, favors missing a near-dupe over blocking a real
    # competitor, same stance as the executive guard.
    COMPETITOR_NAME_SIMILARITY_THRESHOLD = 0.88
    COMPETITOR_NEAR_DUPLICATE_MIN_LENGTH = 5

    # Maximum length for person names
    MAX_PERSON_NAME_LENGTH = 100

    # A2.1 — corporate-descriptor nouns that disqualify a candidate from
    # being a person name (Layer 7 of _is_valid_person_name_layered), for
    # names that aren't caught by strict legal suffixes (_LEGAL_SUFFIXES,
    # e.g. "Inc"/"Corp"/"Ltd") but are still never part of a real human
    # name — confirmed live case: "Varun Beverages" (PepsiCo's actual
    # bottling franchisee, not a person named "Varun" with surname
    # "Beverages"). Checked against all live person-entity names in the DB
    # first — none use any of these words, so this is a zero-risk addition.
    # E7-F3: added "foods", "chemicals", "energy", "international", "financial",
    # "capital", "ventures", "consulting", "pharmaceuticals" -- the same
    # Varun-Beverages class of gap persisted for these ("Varun Foods", "Priya
    # Capital", "Raj Chemicals" all still passed every person-name layer).
    CORPORATE_ENTITY_NOUNS = {
        "beverages", "industries", "motors", "systems", "technologies",
        "enterprises", "partners", "solutions", "labs",
        "foods", "chemicals", "energy", "international", "financial",
        "capital", "ventures", "consulting", "pharmaceuticals",
    }

    # Phase 5 (TASK.md 9-phase) — placeholder/example text that should never
    # reach promotion regardless of shape. "Example Corp." was confirmed live
    # as a promoted Tesla competitor: it passes every existing layer purely on
    # shape (2 title-case tokens, a legal suffix) because no layer checks
    # *content* for "this is a stand-in name, not a real one." Scoped to
    # unambiguous placeholder markers only — deliberately excludes words like
    # "test"/"na"/"xyz" that have real collision risk with legitimate short
    # names or acronyms.
    PLACEHOLDER_TERMS = {
        "example", "sample", "placeholder", "dummy", "lorem", "ipsum",
        "acme", "foo", "bar", "baz", "n/a", "tbd",
    }

    # Near-duplicate guard for executive promotion (E2). Ratio from
    # difflib.SequenceMatcher on normalized (lowercased, whitespace-collapsed)
    # names. Tested against real cases: 0.966 for the live "Uday Ruddaraju" /
    # "Uday Ruddarraju" pair, 0.941 "tim cook"/"tim cooke", 0.947
    # "elon musk"/"elon musck" — all above this threshold. Genuinely distinct
    # names stay below it: "john smith"/"jane smith" 0.8, "john smith"/
    # "john smyth" 0.9, "john smith"/"john smithson" 0.87. Deliberately
    # conservative (favors missing a near-dupe over blocking a real promotion).
    EXECUTIVE_NAME_SIMILARITY_THRESHOLD = 0.93


class EntityDiscoveryEngine:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError as e:
            self.nlp = None
            logger.critical(
                "spacy_model_not_loaded",
                model="en_core_web_sm",
                reason=str(e),
                effect="Executive/competitor discovery will return empty candidates silently."
            )

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

        # Built once per document (whole-table reads), not per ORG entity --
        # same reuse discipline promote_competitor_candidates() already
        # applies per-batch. Needed now that _process_org_entity validates
        # candidates before insertion instead of only at promotion time.
        org_self_reference_terms = self._client_self_reference_terms(db, client_id)
        org_source_terms = self._registered_source_terms(db)

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
                    db, client_id, entity_name, document_id, client_brand,
                    self_reference_terms=org_self_reference_terms,
                    source_terms=org_source_terms,
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
        # Strip possessive suffix ("Jensen Huang's" -> "Jensen Huang") before any
        # matching/creation, mirroring _is_valid_org_name()'s possessive handling,
        # so mentions attach to the same candidate/entity instead of splitting.
        person_name = self._strip_possessive_suffix(person_name)

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
            # Check last-name-only match (E7-F1: previously matched a single
            # token against ANY part of the executive's name -- including
            # the FIRST name -- so a candidate token like "Tim" or "Mark"
            # incorrectly matched a tracked executive's given name and
            # created an EntityMention for the wrong person ("Tim Hortons
            # coffee" -> Tim Cook, "Mark your calendar" -> Mark Zuckerberg).
            # Restricting to the executive's own surname preserves the
            # legitimate journalism pattern of referring to someone by last
            # name alone ("Musk announced...", "Cook said...") while
            # eliminating the cited false positives, which were all first
            # names.
            exec_parts = [p.lower() for p in exec_entity.name.split()]
            cand_parts = [p.lower() for p in person_name.split()]
            if len(cand_parts) == 1 and len(exec_parts) > 1 and cand_parts[0] == exec_parts[-1]:
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
        client_brand: Optional[Entity],
        self_reference_terms: Optional[set] = None,
        source_terms: Optional[set] = None,
    ) -> str:
        """
        Process an ORG entity:
        - Check if known competitor exists
        - If not and passes _is_valid_org_name_layered, create or update
          CompetitorCandidate

        Candidates are now pre-filtered on this path the same way person
        candidates already were (previously this table was intentionally
        unfiltered at creation -- "we create candidates for all ORG
        entities... re-gated at promotion time instead", see
        _calculate_org_confidence()'s docstring). Measured live at 34%
        precision before this change (NLP_AUDIT_REPORT.md Part 1); the
        promotion-time gate (_is_valid_org_name_layered, still called from
        promote_competitor_candidates()) is unchanged and still runs as a
        second check for any pre-existing candidate created before this fix.
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
        
        # Skip publishers / generic industry terms. Narrowed from
        # IGNORED_ORGANIZATIONS to MEDIA_AND_GENERIC_TERMS (A1.5): the old set
        # also contained real operating companies, so a genuine competitor named
        # in an article never even became a CompetitorCandidate. Verified live —
        # Apple Inc had 188 candidates and not one of Microsoft/Google/Amazon
        # among them, despite all three appearing in its document corpus.
        if normalized_name in EntityDiscoveryConfig.MEDIA_AND_GENERIC_TERMS:
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

        # Layered validation of the candidate, mirroring
        # _process_person_entity()'s existing gate. Runs the same
        # promotion-time check (_is_valid_org_name_layered) here instead,
        # before a new row is ever inserted.
        is_valid, reject_layer, reject_reason = self._is_valid_org_name_layered(
            org_name,
            client_name=client_brand.name if client_brand else "",
            self_reference_terms=self_reference_terms,
            source_terms=source_terms,
        )
        if not is_valid:
            logger.info(
                "competitor_candidate_rejected_at_creation",
                client_id=client_id,
                candidate=org_name,
                reason=reject_reason,
                layer=reject_layer,
                confidence=0.0,
                mention_count=1,
                documents=[document_id],
            )
            return "skipped"

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

    def _span_verb_token(self, text: str) -> Optional[str]:
        """
        Real POS-based verb detection, replacing the old hand-maintained
        action-verb denylists on both the person and org validation paths.
        Runs the same spaCy pipeline already loaded (self.nlp) over the
        candidate span alone and returns the first token spaCy's tagger
        marks pos_=="VERB" (any inflected form -- VBZ/VBD/VBP/VBG/VB),
        or None if no token in the span is a verb.

        Deliberately excludes pos_=="AUX" (modal/auxiliary verbs like
        "Will", "Is", "Was") -- verified live against real first names
        ("Will Smith", "May Wong") that spaCy tags as AUX in a short
        Title-Case span, not VERB; excluding AUX avoids rejecting those.

        Honest limitation, verified live: spaCy's tagger loses accuracy on
        a short 2-4 word span taken out of its original sentence context.
        "Trump Locks Down" tags "Locks" as PROPN (not VERB) in isolation,
        and "Frames Autonomy" tags "Frames" as PROPN too -- both still slip
        past this check, same as they did past the old denylist, since
        neither contained a word on that list either. This check is a real
        improvement (catches "Deletes", "Acquires", "Boycotting" without
        needing them hand-added to a list) but is not a complete fix for
        context-free NER spans; see NLP_AUDIT_REPORT.md.
        """
        if not text or not self.nlp:
            return None
        doc = self.nlp(text)
        for tok in doc:
            if tok.pos_ == "VERB":
                return tok.text
        return None

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

        # Layer 3 — Verb Filter (POS-based, replaces the old hardcoded
        # action-verb denylist -- see _span_verb_token()'s docstring for why
        # this is real grammatical detection instead of a word list, and its
        # known limitation on context-free spans).
        verb_hit = self._span_verb_token(name_clean)
        if verb_hit:
            return False, "Layer 3 — Verb Filter", f"Contains a verb: '{verb_hit}'"

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

        # Layer 6 — Generic/Organization Term Filter
        # Reuses the same generic-term list the ORG path already treats as non-entities
        # (media outlets, financial terminals, industry buzzwords like "AI", "GPU", "IPO").
        # A real human name should never be composed of these terms; this catches cases
        # where a headline fragment (e.g. "Moonshot AI") gets NER-mislabeled as PERSON.
        for part in parts:
            p_lower = part.lower().rstrip(".,")
            if p_lower in EntityDiscoveryConfig.IGNORED_ORGANIZATIONS:
                return False, "Layer 6 — Generic/Organization Term Filter", f"Matches generic organization/industry term: '{p_lower}'"

        # Layer 7 — Corporate Entity Noun Filter (A2.1)
        # No layer here previously required a *positive* human-name signal —
        # only negative denylists (verbs, publishers, products, generic org
        # terms). A syntactically valid 2-word Title-Case phrase like "Varun
        # Beverages" cleared every layer above purely on shape, because none
        # of Layers 3-6's denylists contain "beverages". Reuses
        # `_LEGAL_SUFFIXES` (already used elsewhere in this file for the
        # same concept — a word that marks a name as corporate rather than
        # human) rather than duplicating it, extended with common
        # corporate-descriptor nouns that aren't strict legal suffixes but
        # are never part of a real person's name either.
        for part in parts:
            p_lower = part.lower().rstrip(".,")
            if p_lower in self._LEGAL_SUFFIXES or p_lower in EntityDiscoveryConfig.CORPORATE_ENTITY_NOUNS:
                return False, "Layer 7 — Corporate Entity Noun Filter", f"Matches corporate-entity noun: '{p_lower}'"

        return True, "", ""

    def _strip_possessive_suffix(self, name: str) -> str:
        """Strip a trailing possessive ("Jensen Huang's" -> "Jensen Huang"), same
        suffix set _is_valid_org_name() checks for organizations."""
        stripped = name.rstrip()
        for suffix in ("'s", "’s", "s'"):
            if stripped.endswith(suffix):
                return stripped[: -len(suffix)].rstrip()
        return stripped

    def _find_near_duplicate_person_entity(
        self, db: Session, client_id: str, name: str
    ) -> Optional[Entity]:
        """E2 guard: catch spelling-variant duplicates (e.g. "Uday Ruddaraju" vs
        "Uday Ruddarraju") that the exact-match ilike check in
        promote_executive_candidates() won't catch. Scoped to entity_type='person'
        within the same client only, so two different clients' "John Smith"s never
        collide. Not a merge — callers should skip promotion and log for review."""
        normalized = re.sub(r"\s+", " ", name.strip().lower())
        existing_people = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "person"
        ).all()
        for entity in existing_people:
            other_normalized = re.sub(r"\s+", " ", entity.name.strip().lower())
            ratio = SequenceMatcher(None, normalized, other_normalized).ratio()
            if ratio >= EntityDiscoveryConfig.EXECUTIVE_NAME_SIMILARITY_THRESHOLD:
                return entity
        return None

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
        has_exec_context = self._has_executive_context(db, person_name, doc_ids)
        if has_exec_context:
            confidence += 0.15

        # Existing verified executive alias boost: +0.20
        # E7-F2: previously fired on last-name coincidence ALONE -- any
        # candidate sharing a verified executive's surname (e.g. "Emily
        # Huang" vs. a tracked "Jensen Huang") got +0.20 regardless of
        # context, which combined with the boosts above could push an
        # unrelated same-surname person over the promotion threshold on just
        # 2 document appearances. Now also requires the same executive-
        # relevant context signal already checked above as corroboration --
        # a same-surname mention with no executive context nearby is far
        # more likely to be an unrelated person than a real alias of the
        # tracked executive.
        if has_exec_context:
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

    # Legal suffixes that indicate a corporate name *when they terminate it*.
    _LEGAL_SUFFIXES = {
        "inc", "inc.", "corp", "corp.", "corporation", "ltd", "ltd.", "limited",
        "llc", "llc.", "plc", "gmbh", "ag", "sa", "nv", "bv", "co", "co.",
        "company", "holdings", "group",
    }

    def _calculate_org_confidence(self, org_name: str) -> float:
        """
        Confidence score for an organization candidate, from name *shape* only.

        A1.6: the previous version added a flat +0.15 for containing any of
        inc/corp/ltd/llc anywhere in the string. Confirmed live, that inverted
        the ranking — headline fragments and 13F filers ("6th Official Apple
        Inc.", "Lavaca Capital LLC MarketBeat", "Citizens Financial Group Inc.")
        scored 0.85 while every real competitor name capped at the 0.70 base.

        The suffix signal is kept but conditioned on the suffix actually
        *terminating* the name, which is what distinguishes a company name from
        a sentence that happens to contain one. Fragment-shaped names are now
        penalised instead of rewarded.

        NOTE (forward-only): this runs at candidate creation, not on update, so
        it does not rescore the 1,074 candidate rows already stored. Those are
        re-gated by _is_valid_org_name_layered() at promotion time instead.
        """
        base = 0.70
        cleaned = (org_name or "").strip()
        if not cleaned:
            return 0.0

        tokens = [t for t in re.split(r"\s+", cleaned) if t]
        if not tokens:
            return 0.0

        confidence = base

        # Legal suffix, but only as the final token ("Acme Corp." yes;
        # "6th Official Apple Inc." is caught by the fragment penalties below).
        if tokens[-1].lower().rstrip(",") in self._LEGAL_SUFFIXES and len(tokens) >= 2:
            confidence += 0.10

        # Well-formed proper-noun shape: every token starts uppercase or is a
        # lowercase connective ("of", "and", "de"). Headline fragments routinely
        # break this ("the World's Most Valuable Company").
        connectives = {"of", "and", "for", "the", "de", "du", "van", "von", "da"}
        shape_ok = all(
            tok[0].isupper() or tok.lower() in connectives
            for tok in tokens
            if tok and tok[0].isalpha()
        )
        if shape_ok:
            confidence += 0.05
        else:
            confidence -= 0.15

        # Fragment penalties — length and digits are the two strongest
        # sentence-fragment tells in the live candidate sample.
        if len(tokens) >= 4:
            confidence -= 0.15
        elif len(tokens) == 3:
            confidence -= 0.05
        if any(any(ch.isdigit() for ch in tok) for tok in tokens):
            confidence -= 0.10
        if "'" in cleaned or "’" in cleaned:
            confidence -= 0.10

        return max(0.0, min(1.0, round(confidence, 4)))

    def _client_self_reference_terms(self, db: Session, client_id: str) -> set:
        """
        A1.4 — build the client's own-identity term set from data that actually
        exists, rather than a guessed heuristic: the brand Entity's name, its
        ticker_symbol, its EntityAlias rows, and its PRIMARY/ALIAS EntityKeyword
        rows. All four are populated by client_service.onboard_client().

        Verified live: this yields {"apple inc", "apple"} for Apple Inc,
        {"tesla", "tsla"} for Tesla, {"pepsico", "pep"} for PepsiCo.
        """
        terms: set = set()
        brand = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "brand"
        ).first()
        if not brand:
            return terms

        def _add(value):
            if value and str(value).strip():
                terms.add(self._normalize_name(str(value)))

        _add(brand.name)
        _add(brand.ticker_symbol)
        for alias in brand.aliases:
            _add(alias.alias_text)
        for kw in brand.keywords:
            if (kw.category or "").upper() in ("PRIMARY", "ALIAS"):
                _add(kw.keyword_text)

        # The client's own products, from the entity_type the Entity model
        # already documents ('brand', 'person', 'product', 'competitor') and
        # from PRODUCT-category keywords.
        #
        # HONEST LIMITATION — verified live: there are currently zero
        # entity_type='product' rows and zero PRODUCT-category keywords in the
        # database, so this branch is inert today and "iPhones", "iPad",
        # "MacBooks", "Nexon", "Punch" and "Sierra" still pass the gate. No
        # other signal for "this is the client's own product" exists at this
        # point in the pipeline — spaCy tags all of them ORG (verified). Rather
        # than invent a per-client product blocklist, the classifier reads the
        # data source that is supposed to hold this, so the gate starts working
        # the moment onboarding populates it. Logged in FINDINGS.md.
        product_entities = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "product"
        ).all()
        for prod in product_entities:
            _add(prod.name)
            for alias in prod.aliases:
                _add(alias.alias_text)

        product_keywords = db.query(EntityKeyword).join(
            Entity, Entity.id == EntityKeyword.entity_id
        ).filter(
            Entity.client_id == client_id,
            EntityKeyword.category == "PRODUCT"
        ).all()
        for kw in product_keywords:
            _add(kw.keyword_text)

        terms.discard("")
        return terms

    def _is_valid_org_name_layered(
        self,
        org_name: str,
        client_name: str = "",
        self_reference_terms: Optional[set] = None,
        source_terms: Optional[set] = None,
    ) -> tuple:
        """
        Layered organization-name classifier. Returns (is_valid, layer, reason),
        mirroring _is_valid_person_name_layered()'s contract so competitor
        rejections are as observable as executive ones.

        A1.1 — the previous implementation was a pure blocklist: any 4+ character,
        <=4-word noun phrase that missed a ~90-entry set was accepted. Verified
        live, it returned True for every junk competitor in the database
        ("iPhones", "NASDAQ", "Guardian", "AAPL Shares", "Britannica Money",
        "Nexon", "Punch", "Sierra", "Pepsi", "Example Corp.") and False for real
        ones ("Microsoft", "AMD", "BYD").

        A1.2 — investigated and REJECTED: requiring the spaCy ORG label as a
        positive signal, the way PERSON is required for executives. It carries
        zero discriminating power here. Every CompetitorCandidate row is already
        ORG-labelled by construction (_process_document only routes label=="ORG"
        into _process_org_entity), and en_core_web_sm was verified to tag
        "iPhones", "Nexon", "Punch", "AAPL Shares", "NASDAQ", "Guardian" and
        "Britannica Money" all as ORG. The label is an invariant of the table,
        not a classifier input. See FINDINGS.md.
        """
        raw = (org_name or "").strip()
        if not raw:
            return False, "Layer O1 — Shape Validation", "Empty name"

        normalized = self._normalize_name(raw)
        if not normalized:
            return False, "Layer O1 — Shape Validation", "Name normalizes to empty"

        # ── Layer O1 — Shape validation ────────────────────────────────────
        if re.search(r'^https?://', raw) or re.search(r'%[0-9A-F]{2}', raw) or re.search(r'<[^>]+>', raw):
            return False, "Layer O1 — Shape Validation", "Contains URL, HTML or URL encoding"

        if len(raw) > 120:
            return False, "Layer O1 — Shape Validation", f"Length {len(raw)} exceeds organization-name bound"

        if raw.rstrip().endswith(("'s", "’s", "s'")):
            return False, "Layer O1 — Shape Validation", "Possessive form"

        if re.search(r'\.(com|co|net|org|io|in|uk)$', normalized):
            return False, "Layer O1 — Shape Validation", "Name is a web domain"

        tokens = [t for t in re.split(r'\s+', raw) if t]
        if len(tokens) > 4:
            return False, "Layer O1 — Shape Validation", f"{len(tokens)} words — headline/sentence fragment, not a name"

        # A bare legal suffix is not a name ("LLC", "Inc", "Holdings").
        if normalized.lower() in self._LEGAL_SUFFIXES:
            return False, "Layer O1 — Shape Validation", "Bare legal suffix, no organization name"

        # Ordinals only occur in prose ("6th Official Apple Inc."), never in a
        # company name. Deliberately narrower than "starts with a digit", which
        # would reject 3M and 7-Eleven.
        if any(re.fullmatch(r'\d+(st|nd|rd|th)', t.lower().strip('.,')) for t in tokens):
            return False, "Layer O1 — Shape Validation", "Contains an ordinal — sentence fragment"

        # A1.3 — the old rule rejected everything <=3 characters, which blocked
        # AMD, BYD, IBM, GM, HP and Kia. Length alone is not the discriminator;
        # capitalization is. A real short name is an all-caps acronym (AMD, BYD,
        # NIO) or a Title-case word (Kia, Ola). A short lowercase/mixed fragment
        # is not. Bare industry acronyms that survive this (AI, GPU, EV, CPU)
        # are caught by Layer O5, which is what that generic-term list is for.
        if len(normalized) <= 3:
            bare = re.sub(r'[^A-Za-z]', '', raw)
            looks_like_name = bool(bare) and len(bare) >= 2 and (bare.isupper() or bare.istitle())
            if not looks_like_name:
                return False, "Layer O1 — Shape Validation", f"Short non-acronym token: '{raw}'"

        if not re.search(r'[A-Za-z]', normalized):
            return False, "Layer O1 — Shape Validation", "No alphabetic content"

        # ── Layer O1b — Placeholder / example text ─────────────────────────
        # A literal stand-in name ("Example Corp.") passes O1's shape check
        # cleanly -- this rejects on content, not shape. Whole-token match
        # only (never substring), same discipline as O5's per-token check
        # below, so a real name that merely contains these letters as part
        # of a longer word is never caught.
        raw_tokens = {t.lower().rstrip(".,") for t in re.split(r'[\s,.\-]+', raw) if t}
        placeholder_hit = raw_tokens & EntityDiscoveryConfig.PLACEHOLDER_TERMS
        if placeholder_hit:
            return False, "Layer O1b — Placeholder / Example Text", f"Contains placeholder/example marker: {sorted(placeholder_hit)}"

        # ── Layer O1c — Verb Filter (POS-based) ─────────────────────────────
        # Same detector the person path uses (_span_verb_token) -- a real
        # company name is never a verb phrase. Catches "AMG National Trust
        # Bank Acquires New Shares" (Acquires) and "Boycotting American"
        # (Boycotting), which the old org path had no verb check for at all.
        verb_hit = self._span_verb_token(raw)
        if verb_hit:
            return False, "Layer O1c — Verb Filter", f"Contains a verb: '{verb_hit}'"

        # ── Layer O2 — Client self-reference ───────────────────────────────
        # Fixes the prefix-only bug: for a multi-token client name like
        # "Apple Inc", the old single-token rule at the end was skipped
        # entirely, so "Apple" itself passed as a competitor of Apple Inc.
        normalized_lower = normalized.lower()
        terms = {t.lower() for t in (self_reference_terms or set()) if t}
        if client_name:
            terms.add(self._normalize_name(client_name).lower())
        terms.discard("")

        for term in terms:
            if not term:
                continue
            if normalized_lower == term:
                return False, "Layer O2 — Client Self-Reference", f"Matches the client's own identity term '{term}'"
            if normalized_lower.startswith(term + " "):
                return False, "Layer O2 — Client Self-Reference", f"Sub-brand/department of the client ('{term}')"
            # "Tata" for client "Tata Motors" — the candidate is a proper
            # WORD prefix of the client's own name. Requires a space after
            # the candidate inside the term (word-boundary aligned), not a
            # bare character-level startswith: the old check
            # (`term.startswith(normalized_lower)`) matched "pepsi" against
            # "pepsico" too, since "pepsico" literally starts with the
            # characters "pepsi" -- but "PepsiCo" is one fused word with no
            # internal space, so "Pepsi" is a genuinely distinct sub-brand
            # name there, not a shortened way of saying "PepsiCo" the way
            # "Tata" is a shortened way of saying "Tata Motors". Confirmed
            # live: this wrongly rejected "Pepsi", an already-promoted real
            # PepsiCo competitor (FINDINGS.md Phase 6). The space-boundary
            # version still catches "Tata"/"Tata Motors" (term "tata motors"
            # starts with "tata ") while no longer catching "Pepsi"/"PepsiCo".
            if len(normalized_lower) >= 4 and term.startswith(normalized_lower + " "):
                return False, "Layer O2 — Client Self-Reference", f"Prefix of the client's own name '{term}'"

        # ── Layer O3 — Publisher / source registry ─────────────────────────
        # Grounded in the platform's own `sources` table rather than a curated
        # list: if we ingest a feed published by this name, it is a publisher.
        # Verified live — this is what identifies "Guardian" (source
        # "The Guardian World", theguardian.com).
        if source_terms and normalized_lower in {s.lower() for s in source_terms}:
            return False, "Layer O3 — Publisher Registry", "Matches a registered content source/publisher"

        # ── Layer O4 — Media / publisher keyword filter ────────────────────
        media_keywords = {
            "times", "news", "post", "press", "media", "journal",
            "daily", "weekly", "magazine", "wire", "digest",
            "briefing", "insider", "watch", "report", "beat",
            "fool", "alpha", "seeking", "cramer", "street",
        }
        name_words = {w for w in re.split(r'[\s,.\-]+', normalized_lower) if w}
        hit = name_words & media_keywords
        if hit:
            return False, "Layer O4 — Media / Publisher Filter", f"Contains publisher keyword: {sorted(hit)}"

        # ── Layer O5 — Market instrument / venue / generic-term filter ─────
        if normalized_lower in EntityDiscoveryConfig.EXCHANGES_AND_REGULATORS:
            return False, "Layer O5 — Market / Regulator Filter", "Exchange, index or regulatory body"

        noise = name_words & EntityDiscoveryConfig.MARKET_NOISE_TERMS
        if noise:
            return False, "Layer O5 — Market / Regulator Filter", f"Market-instrument phrase: {sorted(noise)}"

        if normalized_lower in EntityDiscoveryConfig.MEDIA_AND_GENERIC_TERMS:
            return False, "Layer O5 — Market / Regulator Filter", "Generic industry/media term"

        # Per-token match is restricted to terms of 4+ characters. The short
        # entries in this set are bare industry acronyms ("ai", "ev", "gpu",
        # "pr") that legitimately appear *inside* real company names — matching
        # them per-token rejected "Mistral AI". Whole-name matching above still
        # catches them when they stand alone.
        for word in name_words:
            if len(word) >= 4 and word in EntityDiscoveryConfig.MEDIA_AND_GENERIC_TERMS:
                return False, "Layer O5 — Market / Regulator Filter", f"Generic industry/media term: '{word}'"

        return True, "", ""

    def _is_valid_org_name(
        self,
        org_name: str,
        client_name: str = "",
        self_reference_terms: Optional[set] = None,
        source_terms: Optional[set] = None,
    ) -> bool:
        """Boolean wrapper over _is_valid_org_name_layered() — signature kept
        backwards-compatible so existing call sites and the audit's direct-invoke
        verification technique both keep working."""
        is_valid, _layer, _reason = self._is_valid_org_name_layered(
            org_name,
            client_name=client_name,
            self_reference_terms=self_reference_terms,
            source_terms=source_terms,
        )
        return is_valid

    def _registered_source_terms(self, db: Session) -> set:
        """
        A1.3/O3 helper — publisher names derived from the platform's own source
        registry ("The Guardian World" -> theguardian.com -> "guardian").

        Per-client search feeds are excluded. Onboarding creates one source per
        client named after the client ("Apple Inc RSS Source", "Tesla GDELT
        Feed"), so without this exclusion every client's own brand would look
        like a publisher — and, worse, would be rejected as a competitor of
        every *other* client. Verified: this is what wrongly rejected "Apple"
        for Nvidia and OpenAI on the first run of the A3 re-validation.

        The exclusion is grounded in the `clients` table plus the brand entity
        names, not a guess about feed naming.
        """
        from app.models.source import Source

        feed_word_pattern = re.compile(
            r'\b(rss|feed|feeds|source|gdelt|algolia|hn|google news|json|api)\b',
            re.IGNORECASE,
        )

        client_owned: set = set()
        try:
            for (client_name,) in db.query(Client.name).all():
                if client_name:
                    client_owned.add(self._normalize_name(client_name))
            brand_names = db.query(Entity.name).filter(Entity.entity_type == "brand").all()
            for (brand_name,) in brand_names:
                if brand_name:
                    client_owned.add(self._normalize_name(brand_name))
        except Exception as exc:
            logger.warning("competitor_source_client_names_unavailable", error=str(exc))
        client_owned.discard("")

        terms: set = set()
        try:
            for src in db.query(Source.name, Source.url).all():
                name = (src.name or "").strip()
                if not name:
                    continue
                cleaned = feed_word_pattern.sub(" ", name)
                cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                if not cleaned:
                    continue
                normalized = self._normalize_name(cleaned)
                if not normalized:
                    continue

                candidate_terms = {normalized}
                # "The Guardian World" -> also register "guardian": drop a
                # leading article and keep the leading proper noun.
                parts = [p for p in normalized.split() if p not in ("the", "a", "an")]
                if parts:
                    candidate_terms.add(parts[0])
                    candidate_terms.add(" ".join(parts))

                # Skip this source entirely if it is a client's own search feed.
                if candidate_terms & client_owned:
                    continue
                terms |= candidate_terms
        except Exception as exc:
            logger.warning("competitor_source_terms_unavailable", error=str(exc))
        terms.discard("")
        return terms

    def _find_near_duplicate_competitor_entity(
        self, db: Session, client_id: str, name: str
    ) -> Optional[Entity]:
        """
        A1.7 — competitor-scoped analogue of _find_near_duplicate_person_entity().
        Blocks split identities such as "General Motors"/"General Motor" and
        "Ford"/"Fords" from becoming two competitor rows in the same benchmark.
        Not a merge — callers skip promotion and log for review, same stance as
        the executive guard.
        """
        normalized = self._normalize_name(name)
        if len(normalized) < EntityDiscoveryConfig.COMPETITOR_NEAR_DUPLICATE_MIN_LENGTH:
            return None
        existing = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "competitor"
        ).all()
        for entity in existing:
            other = self._normalize_name(entity.name)
            if len(other) < EntityDiscoveryConfig.COMPETITOR_NEAR_DUPLICATE_MIN_LENGTH:
                continue
            ratio = SequenceMatcher(None, normalized, other).ratio()
            if ratio >= EntityDiscoveryConfig.COMPETITOR_NAME_SIMILARITY_THRESHOLD:
                return entity
        return None

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

        # Built once per batch, not per candidate — both are whole-table reads.
        self_reference_terms = self._client_self_reference_terms(db, client_id)
        source_terms = self._registered_source_terms(db)

        for candidate in candidates:
            # Gate: must look like a real company, not a publisher, market
            # instrument, generic term, or the client's own brand/sub-brand.
            is_valid, reject_layer, reject_reason = self._is_valid_org_name_layered(
                candidate.organization_name,
                client_name=client.name if client else "",
                self_reference_terms=self_reference_terms,
                source_terms=source_terms,
            )
            if not is_valid:
                logger.info(
                    "competitor_candidate_rejected",
                    client_id=client_id,
                    candidate_name=candidate.organization_name,
                    layer=reject_layer,
                    reason=reject_reason,
                    confidence=candidate.confidence,
                    mention_count=candidate.mention_count,
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
                    # A1.7 near-duplicate guard: block a spelling/plural variant
                    # of an already-promoted competitor ("General Motor" next to
                    # "General Motors") from becoming a second row in the same
                    # benchmark. Skip and log for review rather than auto-merging,
                    # same stance as the executive E2 guard.
                    near_dup = self._find_near_duplicate_competitor_entity(
                        db, client_id, candidate.organization_name
                    )
                    if near_dup:
                        logger.warning(
                            "competitor_candidate_near_duplicate_blocked",
                            client_id=client_id,
                            candidate_name=candidate.organization_name,
                            existing_entity_id=str(near_dup.id),
                            existing_entity_name=near_dup.name,
                            reason="Name is a near-duplicate of an existing promoted competitor "
                                   "for this client — needs manual review before promoting or "
                                   "merging, not auto-promoted."
                        )
                        continue

                    # Advisory locks above cover candidate creation/update, not this
                    # promotion path — two concurrent promotion calls could both reach
                    # here for the same candidate. SAVEPOINT-isolate the insert (same
                    # per-item isolation pattern as executive_reputation_engine.py's
                    # db.begin_nested()) so a uq_entities_client_name collision only
                    # rolls back this one candidate, not the whole batch, and recover
                    # by treating it as "already promoted by the other transaction."
                    savepoint = db.begin_nested()
                    try:
                        new_entity = Entity(
                            client_id=client_id,
                            name=candidate.organization_name,
                            entity_type="competitor"
                        )
                        db.add(new_entity)
                        db.flush()  # Get the ID
                    except IntegrityError:
                        savepoint.rollback()
                        client_entities = db.query(Entity).filter(Entity.client_id == client_id).all()
                        existing_entity = next((e for e in client_entities if self._normalize_name(e.name) == normalized_cand_name), None)
                        if existing_entity:
                            candidate.promoted_to_competitor_id = existing_entity.id
                            candidate.promoted_at = datetime.now(timezone.utc)
                            logger.info(
                                "competitor_candidate_linked_to_concurrently_promoted_entity",
                                client_id=client_id,
                                candidate_name=candidate.organization_name,
                                entity_id=str(existing_entity.id)
                            )
                        continue
                    savepoint.commit()

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

            # Check if entity already exists (strip any possessive suffix carried
            # over from a candidate created before the entry-point fix, so it
            # matches/creates under the canonical name rather than splitting)
            promoted_name = self._strip_possessive_suffix(candidate.name)
            existing_entity = db.query(Entity).filter(
                Entity.client_id == client_id,
                Entity.name.ilike(promoted_name),
                Entity.entity_type == "person"
            ).first()

            if not existing_entity:
                # E2 guard: block promotion of a near-duplicate spelling variant of
                # an already-promoted executive (same class of bug P1-B fixed for
                # possessive suffixes). Skip and log for manual review rather than
                # auto-merging — no existing "needs review" flag/state on
                # ExecutiveCandidate to use instead, and inventing a merge here
                # risks a false-positive merge of two genuinely different people.
                near_dup = self._find_near_duplicate_person_entity(db, client_id, promoted_name)
                if near_dup:
                    logger.warning(
                        "executive_candidate_near_duplicate_blocked",
                        candidate=candidate.name,
                        normalized_candidate=promoted_name,
                        existing_entity_id=str(near_dup.id),
                        existing_entity_name=near_dup.name,
                        reason="Name is a near-duplicate spelling variant of an existing promoted "
                               "executive for this client — needs manual review before promoting "
                               "or merging, not auto-promoted."
                    )
                    continue

                # Same concurrent-promotion race as promote_competitor_candidates()
                # (advisory locks cover candidate creation/update, not this promotion
                # path) — SAVEPOINT-isolate the insert so a uq_entities_client_name
                # collision only rolls back this one candidate, not the whole batch.
                savepoint = db.begin_nested()
                try:
                    new_entity = Entity(
                        client_id=client_id,
                        name=promoted_name,
                        entity_type="person"
                    )
                    db.add(new_entity)
                    db.flush()  # Get the ID
                except IntegrityError:
                    savepoint.rollback()
                    existing_entity = db.query(Entity).filter(
                        Entity.client_id == client_id,
                        Entity.name.ilike(promoted_name),
                        Entity.entity_type == "person"
                    ).first()
                    if existing_entity:
                        candidate.promoted_to_executive_id = existing_entity.id
                        candidate.promoted_at = datetime.now(timezone.utc)
                        logger.info(
                            "executive_candidate_linked_to_concurrently_promoted_entity",
                            candidate=candidate.name,
                            entity_id=str(existing_entity.id)
                        )
                    continue
                savepoint.commit()

                new_keyword = EntityKeyword(
                    entity_id=new_entity.id,
                    keyword_text=promoted_name,
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
