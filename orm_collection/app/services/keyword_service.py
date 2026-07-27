from sqlalchemy.orm import Session
from app.models.entity import EntityKeyword
from typing import List

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
        
    # Example: If base_name has " Inc" or " LLC", add a version without it
    if " Inc" in base_name or " LLC" in base_name or " Ltd" in base_name:
        clean_name = base_name.replace(" Inc", "").replace(" LLC", "").replace(" Ltd", "").strip()
        keywords.append(EntityKeyword(
            entity_id=entity_id,
            keyword_text=clean_name,
            category="ALIAS",
            priority=8
        ))

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

