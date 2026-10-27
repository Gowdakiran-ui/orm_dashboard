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


def is_relevant(title: Optional[str], content: Optional[str], terms: Iterable[str], source: Optional[str] = None) -> bool:
    """True when the title or summary contains the brand or any tracked name as whole words.
    `terms` may be a RelevanceRules (bare-alias context rule, see below); `source` is the backfill source name."""
    if isinstance(terms, RelevanceRules):
        return terms.matches(title, content, source)
    text = _norm(title) + _norm(content)
    return any(t in text for t in terms)


_RISK_NORMED = [_norm(t) for t in RISK_TERMS]


def has_risk_term(title: Optional[str], content: Optional[str]) -> bool:
    text = _norm(title) + _norm(content)
    return any(t in text for t in _RISK_NORMED)


# Query-kind priority for collection: brand and risk words first, then people, competitors/products last.
KIND_PRIORITY = {"brand": 0, "risk": 0, "executive": 1, "competitor": 2, "product": 3}
SOURCE_PRIORITY = {"google_news": 0, "hn": 1, "gdelt": 2, "youtube": 3}


# --------------------------------------------------- bare-alias context rule (backfill filter only)
# Onboarding adds the legal name without its suffix as an alias ("Sobha Limited" -> "Sobha"). That alias is what makes
# old press copy findable, but it also matches other companies that share the word ("Sobha Realty", Dubai). In the
# BACKFILL filter only (not the live matcher, not keyword generation), an item that matches ONLY the bare alias must
# also carry a context term; YouTube is stricter: the context term must be in the title, and any per-client
# exclude term (for example "dubai", "sobha realty") rejects the item.
#
# Per-client override: BACKFILL_ALIAS_CONTEXT_JSON='{"Sobha Limited": {"context": ["bengaluru", ...], "exclude": ["dubai"]}}'
# (key = client name, lower-cased, or client id; "context" replaces the default list, "exclude" is empty by default).
DEFAULT_ALIAS_CONTEXT_TERMS = (
    "limited", "ltd", "pvt", "private limited", "nse", "bse", "rera", "sebi", "india", "indian", "crore", "lakh",
    "stock", "shares", "share price", "dividend", "q1", "q2", "q3", "q4", "fy",
    "bengaluru", "bangalore", "mumbai", "delhi", "ncr", "gurugram", "gurgaon", "noida", "pune", "chennai", "hyderabad",
    "kolkata", "kochi", "kerala", "thrissur", "coimbatore", "karnataka", "maharashtra", "tamil nadu", "gujarat",
)


def alias_context_config(client_id, client_name: Optional[str]) -> dict:
    """{"context": [...normalised...], "exclude": [...normalised...]} for this client (defaults + env override)."""
    import json
    import os
    context, exclude = list(DEFAULT_ALIAS_CONTEXT_TERMS), []
    raw = os.environ.get("BACKFILL_ALIAS_CONTEXT_JSON", "").strip()
    if raw:
        try:
            cfg = json.loads(raw)
            mine = cfg.get(str(client_id)) or cfg.get((client_name or "").strip().lower())
            if mine is None:
                mine = next((v for k, v in cfg.items() if k.strip().lower() == (client_name or "").strip().lower()), None)
            if isinstance(mine, dict):
                context = list(mine.get("context", context))
                exclude = list(mine.get("exclude", exclude))
        except (ValueError, AttributeError, TypeError):
            pass                       # a bad value never breaks collection: the defaults apply
    return {"context": [_norm(t) for t in context if t], "exclude": [_norm(t) for t in exclude if t]}


class RelevanceRules:
    """`full` terms always make an item relevant; a `bare` alias needs a context term (see the block above)."""

    def __init__(self, full: List[str], bare: List[str], context: List[str], exclude: List[str]):
        self.full, self.bare, self.context, self.exclude = list(full), list(bare), list(context), list(exclude)

    def __bool__(self) -> bool:
        return bool(self.full or self.bare)

    def matches(self, title: Optional[str], content: Optional[str], source: Optional[str] = None) -> bool:
        title_n = _norm(title)
        text = title_n + _norm(content)
        if any(t in text for t in self.full):
            return True
        if not any(t in text for t in self.bare):
            return False
        youtube = (source or "").lower() == "youtube"
        haystack = title_n if youtube else text
        if youtube and any(t in text for t in self.exclude):
            return False
        if not youtube and any(t in text for t in self.exclude) and not any(t in text for t in self.context):
            return False
        return any(t in haystack for t in self.context)


def relevance_rules(db, client_id, include_competitors: bool = False, include_products: bool = False) -> RelevanceRules:
    """tracked_terms split into full names and bare stripped aliases. A client with no stripped alias behaves exactly as before."""
    from app.models.client import Client
    from app.models.entity import Entity
    from app.services.keyword_service import strip_legal_suffix

    terms = tracked_terms(db, client_id, include_competitors, include_products)
    bare = set()
    for e in db.query(Entity).filter(Entity.client_id == client_id).all():
        clean = strip_legal_suffix(e.name or "")
        if clean:
            bare.add(_norm(clean))
            bare.add(_norm(clean.replace(" ", "")))
    bare = {b for b in bare if b in terms}
    name = db.query(Client.name).filter(Client.id == client_id).scalar()
    cfg = alias_context_config(client_id, name)
    return RelevanceRules([t for t in terms if t not in bare], sorted(bare), cfg["context"], cfg["exclude"])
