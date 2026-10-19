"""Relevance filter and priority helpers (pure functions plus one DB read)."""
import re
from typing import Iterable, List, Optional

from app.services.backfill.queries import RISK_TERMS


def _norm(text: Optional[str]) -> str:
    """Lower-case, punctuation to single spaces, padded so phrases match on word boundaries."""
    return " " + re.sub(r"[\W_]+", " ", (text or "").lower()).strip() + " "


def tracked_terms(db, client_id, include_competitors: bool = False, include_products: bool = False) -> List[str]:
    """
    Names this client is actually tracked under: the brand and tracked people always,
    competitors/products only when the matching backfill flag is on. Entity names, aliases
    and PRIMARY/ALIAS keywords only (EXECUTIVE and RISK keyword rows are generic phrases
    such as "CEO of X" or "X fraud" and would let noise through).
    """
    from app.models.entity import Entity, EntityAlias, EntityKeyword
    types = {"brand", "person"}
    if include_competitors:
        types.add("competitor")
    if include_products:
        types.add("product")
    ents = [e for e in db.query(Entity).filter(Entity.client_id == client_id).all()
            if (e.entity_type or "").lower() in types]
    ids = [e.id for e in ents]
    terms = {e.name for e in ents}
    if ids:
        terms.update(a.alias_text for a in db.query(EntityAlias).filter(EntityAlias.entity_id.in_(ids)).all())
        terms.update(
            k.keyword_text for k in db.query(EntityKeyword).filter(
                EntityKeyword.entity_id.in_(ids), EntityKeyword.is_active == True,   # noqa: E712
                EntityKeyword.category.in_(("PRIMARY", "ALIAS")),
            ).all()
        )
    out = sorted({_norm(t) for t in terms if t and len(t.strip()) >= 3})
    return [t for t in out if t.strip()]


def is_relevant(title: Optional[str], content: Optional[str], terms: Iterable[str]) -> bool:
    """True when the title or summary contains the brand or any tracked name as whole words."""
    text = _norm(title) + _norm(content)
    return any(t in text for t in terms)


_RISK_NORMED = [_norm(t) for t in RISK_TERMS]


def has_risk_term(title: Optional[str], content: Optional[str]) -> bool:
    text = _norm(title) + _norm(content)
    return any(t in text for t in _RISK_NORMED)


# Query-kind priority for collection: brand and risk words first, then people, competitors/products last.
KIND_PRIORITY = {"brand": 0, "risk": 0, "executive": 1, "competitor": 2, "product": 3}
SOURCE_PRIORITY = {"google_news": 0, "hn": 1, "gdelt": 2, "youtube": 3}
