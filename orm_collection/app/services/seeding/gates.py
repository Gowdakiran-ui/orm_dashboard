"""
Seeded-entity document gates, used by the executive and benchmark engines in place of the brand-entity gate.

- SEEDED executive: a document counts when the person's full name (or an enabled multi-word alias) AND the company name
  both appear in the document's title or summary (first LEAD_CHARS characters of the stored text).
- SEEDED competitor: a document counts when it is about the competitor itself: its full name appears in the title or
  summary and, for a one-word name, a sector (context) word appears in the text. It does not need to mention the client.

Non-seeded entities keep the existing gates unchanged.
"""
from typing import Dict, Iterable, List, Optional, Set

from sqlalchemy import func

LEAD_CHARS = 600


def _norm(text: Optional[str]) -> str:
    from app.services.backfill.relevance import _norm as n
    return n(text)


def table_exists(db) -> bool:
    """False until migration 0016 is applied; every caller then behaves exactly as before seeding existed."""
    from sqlalchemy import inspect
    try:
        return inspect(db.get_bind()).has_table("seeded_entities")
    except Exception:
        return False


def seeded_rows(db, client_id, kind: Optional[str] = None):
    from app.models.seeded_entity import SeededEntity
    if not table_exists(db):
        return []
    q = db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.status == "active",
                                      SeededEntity.entity_id.isnot(None))
    if kind:
        q = q.filter(SeededEntity.kind == kind)
    return q.order_by(SeededEntity.kind.desc(), SeededEntity.rank).all()      # executives, then competitors; each in seed order


def seeded_entity_ids(db, client_id, kind: Optional[str] = None) -> Set:
    return {r.entity_id for r in seeded_rows(db, client_id, kind)}


def enabled_alias_texts(row) -> List[str]:
    out = []
    for a in (row.aliases or []):
        if isinstance(a, dict) and a.get("enabled") and a.get("alias"):
            out.append(a["alias"])
    return out


def company_terms(db, client_id) -> List[str]:
    """Normalised names the client goes by: brand entity name and aliases."""
    from app.models.entity import Entity, EntityAlias
    brands = db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == "brand").all()
    terms = {b.name for b in brands}
    ids = [b.id for b in brands]
    if ids:
        terms.update(a.alias_text for a in db.query(EntityAlias).filter(EntityAlias.entity_id.in_(ids)).all())
    return sorted({_norm(t) for t in terms if t and len(t.strip()) >= 3})


def _lead_rows(db, entity_id, context_words=None):
    """(document id, title, first LEAD_CHARS characters[, context hit]) for the documents mentioning the entity. With
    `context_words`, a fourth value says whether any of them appears anywhere in the stored text."""
    from sqlalchemy import or_
    from app.models.document import Document
    from app.models.entity import EntityMention
    cols = [Document.id, Document.title, func.substr(Document.normalized_content, 1, LEAD_CHARS)]
    if context_words:
        from sqlalchemy import case
        hit = or_(*[func.lower(Document.normalized_content).like(f"%{w.lower()}%") for w in context_words])
        cols.append(case((hit, 1), else_=0))
    return db.query(*cols).join(EntityMention, EntityMention.document_id == Document.id).filter(
        EntityMention.entity_id == entity_id).distinct().all()


def person_doc_ids(rows: Iterable, name_terms: List[str], co_terms: List[str]) -> Set:
    """Pure: documents whose title/lead holds a full-name term and a company term."""
    names = [_norm(t) for t in name_terms if t]
    cos = [_norm(t) for t in co_terms if t]
    out = set()
    for doc_id, title, lead in rows:
        text = _norm(title) + _norm(lead)
        if any(n in text for n in names) and any(c in text for c in cos):
            out.add(doc_id)
    return out


def competitor_doc_ids(rows: Iterable, name_terms: List[str], context_terms: List[str]) -> Set:
    """Pure: documents about the competitor itself (see module docstring)."""
    names = [_norm(t) for t in name_terms if t]
    ctx = [_norm(t) for t in context_terms if t]
    out = set()
    for row in rows:
        doc_id, title, lead = row[0], row[1], row[2]
        ctx_hit = bool(row[3]) if len(row) > 3 else False
        text = _norm(title) + _norm(lead)
        for n in names:
            if n in text:
                one_word = len(n.split()) < 2
                if (not one_word) or ctx_hit or any(c in text for c in ctx):
                    out.add(doc_id)
                    break
    return out


def seeded_gate_doc_ids(db, client_id, entity_ids: Iterable) -> Dict:
    """{entity_id: set(document ids)} for the seeded entities among `entity_ids`. Other entities are absent."""
    wanted = set(entity_ids)
    out: Dict = {}
    rows = [r for r in seeded_rows(db, client_id) if r.entity_id in wanted]
    if not rows:
        return out
    co = company_terms(db, client_id)
    for r in rows:
        aliases = enabled_alias_texts(r)
        if r.kind == "executive":
            out[r.entity_id] = person_doc_ids(_lead_rows(db, r.entity_id), [r.name] + aliases, co)
        else:
            # context words (any one of them, 4+ letters) rather than the whole phrase, which rarely appears verbatim.
            # The full name must be in the title/summary; for a one-word name a context word may be anywhere in the text.
            ctx = [w for w in _norm(r.context_term).split() if len(w) >= 4] if r.context_term else []
            out[r.entity_id] = competitor_doc_ids(_lead_rows(db, r.entity_id, ctx), [r.name] + aliases, ctx)
    return out


def seeded_feed_urls(db, client_id) -> set:
    """Search-feed URLs provisioned for the client's active seeded entities (what the per-run cap applies to)."""
    from app.models.entity import Entity
    from app.services.client_service import entity_search_feed_urls
    rows = seeded_rows(db, client_id)
    if not rows:
        return set()
    names = {e.id: e.name for e in db.query(Entity).filter(Entity.id.in_([r.entity_id for r in rows])).all()}
    brand = next(iter(company_terms(db, client_id)), None)
    brand_row = db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == "brand").first()
    company = brand_row.name if brand_row else brand
    urls = set()
    for r in rows:
        name = names.get(r.entity_id)
        if not name:
            continue
        co = company if r.kind == "executive" else (r.context_term or None)
        urls.update(entity_search_feed_urls(name, co_occur_with=co, quote=True, co_quoted=(r.kind == "executive")).values())
    return urls
