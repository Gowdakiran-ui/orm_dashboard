from sqlalchemy.orm import Session
from app.models.entity import EntityKeyword
from typing import List, Optional
import logging
import re

logger = logging.getLogger(__name__)

# Pure legal-form words only. Dropped from the END of a name, repeatedly ("Pvt Ltd").
_LEGAL_SUFFIXES = {
    "limited", "ltd", "pvt", "private", "inc", "incorporated", "llc", "llp", "corporation",
    "corp", "co", "plc", "enterprises", "company",
}
_MIN_STRIPPED_LEN = 4


def strip_legal_suffix(name: str) -> Optional[str]:
    """Name minus trailing legal-form words, or None if nothing was stripped or the result is shorter than 4 characters."""
    tokens = name.strip().split()
    while tokens and re.sub(r"[^\w]", "", tokens[-1]).lower() in _LEGAL_SUFFIXES:
        tokens.pop()
    clean = " ".join(tokens).strip(" ,.&-")
    if not clean or clean == name.strip() or len(clean) < _MIN_STRIPPED_LEN:
        return None
    return clean

def generate_keywords_for_entity(db: Session, entity_id: str, base_name: str) -> List[EntityKeyword]:
    """
    Automated keyword generation based on the primary entity name.
    """
    keywords = []
    
    # 1. PRIMARY
    keywords.append(EntityKeyword(
        entity_id=entity_id,
        keyword_text=base_name,
        category="PRIMARY",
        priority=10
    ))
    
    # 2. ALIAS (basic variations, lowercase, etc.)
    alias_1 = base_name.lower()
    if alias_1 != base_name:
        keywords.append(EntityKeyword(
            entity_id=entity_id,
            keyword_text=alias_1,
            category="ALIAS",
            priority=5
        ))

    # 2b. No-space concatenation (e.g. "Ease My Trip" -> "EaseMyTrip").
    # FlashText matches literal substrings only, no whitespace normalization —
    # a multi-word brand written as one token in the press (confirmed live:
    # EaseMyTrip's own press overwhelmingly uses "EaseMyTrip", not "Ease My
    # Trip") was silently invisible to matching with only the spaced form
    # generated. See FINDINGS.md TASK.md Item 2/Phase 2.
    no_space = base_name.replace(" ", "")
    if " " in base_name and no_space not in (base_name, alias_1):
        keywords.append(EntityKeyword(
            entity_id=entity_id,
            keyword_text=no_space,
            category="ALIAS",
            priority=5
        ))

    # 2c. Name without legal suffixes (e.g. "Sobha Limited" -> "Sobha"). Press copy almost
    # never writes the legal suffix; the relevance filter dropped ~90% of items for that
    # reason. Replaces the older substring check (" Inc"/" LLC"/" Ltd"), which also fired
    # inside words such as "Incredible" and never handled "Limited".
    clean_name = strip_legal_suffix(base_name)
    if clean_name:
        variants = [clean_name]
        if " " in clean_name:
            variants.append(clean_name.replace(" ", ""))
        existing = {k.keyword_text for k in keywords}
        for v in variants:
            if v not in existing:
                keywords.append(EntityKeyword(
                    entity_id=entity_id,
                    keyword_text=v,
                    category="ALIAS",
                    priority=8
                ))
        logger.info("Generated name variants for %r: %s", base_name, variants)

    # 3. EXECUTIVE
    keywords.append(EntityKeyword(
        entity_id=entity_id,
        keyword_text=f"CEO of {base_name}",
        category="EXECUTIVE",
        priority=7
    ))

    # 4. RISK
    risk_terms = ["lawsuit", "scandal", "fraud", "bankruptcy"]
    for term in risk_terms:
        keywords.append(EntityKeyword(
            entity_id=entity_id,
            keyword_text=f"{base_name} {term}",
            category="RISK",
            priority=9
        ))

    db.add_all(keywords)
    db.commit()
    
    try:
        from app.utils.redis_client import redis_client
        redis_client.publish('keyword_updated', 'refresh')
    except Exception:
        pass

    return keywords

def add_keyword(db: Session, entity_id: str, keyword_text: str, category: str, priority: int = 1) -> EntityKeyword:
    db_keyword = EntityKeyword(
        entity_id=entity_id,
        keyword_text=keyword_text,
        category=category,
        priority=priority
    )
    db.add(db_keyword)
    db.commit()
    db.refresh(db_keyword)
    
    try:
        from app.utils.redis_client import redis_client
        redis_client.publish('keyword_updated', 'refresh')
    except Exception:
        pass

    return db_keyword

