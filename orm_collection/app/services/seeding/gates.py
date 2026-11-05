"""
Seeded-entity document gates, used by the executive and benchmark engines in place of the brand-entity gate.

- SEEDED executive: a document counts when the person's full name (or an enabled multi-word alias) AND the company name
  both appear in the document's title or summary (first LEAD_CHARS characters of the stored text), OR when the executive's own
  "Name" "Company" search returned it (a document_feed_hits row) and the stored text holds the company, the surname or a role
  word (guard_passes). The search matches the full article, but only the headline and summary are stored, so the name is often
  only in the body; a sample of 24 such articles read in full named the person in all 24 (reports/).
- SEEDED competitor: a document counts when it passes EITHER gate (the union): the brand co-occurrence gate every competitor has
  (the document mentions the competitor and the client's brand/product), or the self-coverage gate: the competitor's full name
  appears in the title or summary and, for a one-word name, a sector (context) word appears in the text. The second gate alone
  dropped real articles whose stored text lacks the name or the sector word (DLF 15 to 1, Lodha 12 to 1 on a local copy).

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


def hits_table_exists(db) -> bool:
    """False until migration 0017 is applied; the hit-based attribution is then simply absent."""
    from sqlalchemy import inspect
    try:
        return inspect(db.get_bind()).has_table("document_feed_hits")
    except Exception:
        return False


ROLE_WORDS = ("ceo", "cfo", "coo", "md", "managing director", "chief executive", "chief financial", "chairman", "chairperson",
              "chairwoman", "chair", "promoter", "founder", "co founder", "cofounder", "director", "president", "executive")


def guard_passes(title: Optional[str], lead: Optional[str], company_terms_: Iterable[str], name: str) -> bool:
    """Pure. A document returned by an executive's own search is attributed to the person only when the stored title/summary holds
    the company name, the surname or a role word, so a document the search returned for some unrelated reason is not."""
    text = _norm(title) + _norm(lead)
    parts = _norm(name).split()
    surname = parts[-1] if parts else ""
    cos = [_norm(c) for c in company_terms_ if c]
    if any(c in text for c in cos):
        return True
    if len(surname) >= 3 and (" " + surname + " ") in text:
        return True
    return any((" " + w + " ") in text for w in ROLE_WORDS)


def count_hits_enabled() -> bool:
    from app.core.config import settings
    return bool(getattr(settings, "SEEDED_COUNT_SEARCH_HITS", False))


def hit_doc_ids(db, entity_id) -> Set:
    if not hits_table_exists(db):
        return set()
    from app.models.document_feed_hit import DocumentFeedHit
    return {r[0] for r in db.query(DocumentFeedHit.document_id).filter(DocumentFeedHit.entity_id == entity_id).all()}


def uncounted_hit_counts(db, entity_ids: Iterable, window_days: int) -> Dict:
    """{entity_id: N}: documents this executive's own search returned (document_feed_hits) inside the window that carry NO mention of
    them, so they are not in the score. Display only. With SEEDED_COUNT_SEARCH_HITS on, attributed documents have a mention and drop out.
    Window date = the document's published_at, else the time the hit was recorded. 0 for everyone until migration 0017 is applied."""
    import datetime as dt
    ids = list(entity_ids)
    out = {i: 0 for i in ids}
    if not ids or not hits_table_exists(db):
        return out
    from app.models.document import Document
    from app.models.document_feed_hit import DocumentFeedHit
    from app.models.entity import EntityMention
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(window_days))
    mentioned = db.query(EntityMention.id).filter(EntityMention.document_id == DocumentFeedHit.document_id,
                                                  EntityMention.entity_id == DocumentFeedHit.entity_id).exists()
    rows = db.query(DocumentFeedHit.entity_id, func.count(func.distinct(DocumentFeedHit.document_id))).join(
        Document, Document.id == DocumentFeedHit.document_id).filter(
        DocumentFeedHit.entity_id.in_(ids), ~mentioned,
        func.coalesce(Document.published_at, DocumentFeedHit.seen_at) >= cutoff).group_by(DocumentFeedHit.entity_id).all()
    for eid, n in rows:
        out[eid] = int(n)
    return out


def seeded_rows(db, client_id, kind: Optional[str] = None):
    from app.models.seeded_entity import SeededEntity
    if not table_exists(db):
        return []
    q = db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.status == "active",
                                      SeededEntity.entity_id.isnot(None))
    if kind:
        q = q.filter(SeededEntity.kind == kind)
    return q.order_by(SeededEntity.kind.desc(), SeededEntity.rank).all()      # executives, then competitors; each in seed order


def retired_entity_ids(db, client_id) -> Set:
    """Entities whose seeded row was retired and that have no active seeded row. They stay in the database but are not shown on the
    Competitor Compare or Executives pages. Empty before migration 0016."""
    from app.models.seeded_entity import SeededEntity
    if not table_exists(db):
        return set()
    rows = db.query(SeededEntity.entity_id, SeededEntity.status).filter(
        SeededEntity.client_id == client_id, SeededEntity.entity_id.isnot(None)).all()
    active = {e for e, st in rows if st == "active"}
    return {e for e, st in rows if st == "retired"} - active


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


def brand_cooccurring_doc_ids(db, client_id, entity_id) -> Set:
    """The old competitor gate: documents that mention this entity and also the client's brand or product entity."""
    from app.models.entity import Entity, EntityMention
    brand_ids = [b[0] for b in db.query(Entity.id).filter(Entity.client_id == client_id, Entity.entity_type.in_(("brand", "product"))).all()]
    if not brand_ids:
        return set()
    mine = db.query(EntityMention.document_id).filter(EntityMention.entity_id == entity_id)
    theirs = db.query(EntityMention.document_id).filter(EntityMention.entity_id.in_(brand_ids))
    return {r[0] for r in mine.intersect(theirs).all()}


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
            rows_ = _lead_rows(db, r.entity_id)
            base = person_doc_ids(rows_, [r.name] + aliases, co)
            hits = hit_doc_ids(db, r.entity_id) if count_hits_enabled() else set()
            extra = {d for (d, t, l) in rows_ if d in hits and d not in base and guard_passes(t, l, co, r.name)} if hits else set()
            out[r.entity_id] = base | extra
        else:
            # context words (any one of them, 4+ letters) rather than the whole phrase, which rarely appears verbatim.
            # The full name must be in the title/summary; for a one-word name a context word may be anywhere in the text.
            ctx = [w for w in _norm(r.context_term).split() if len(w) >= 4] if r.context_term else []
            own = competitor_doc_ids(_lead_rows(db, r.entity_id, ctx), [r.name] + aliases, ctx)
            out[r.entity_id] = own | brand_cooccurring_doc_ids(db, client_id, r.entity_id)       # union: either gate counts
    return out


def multiword_alias_texts(row) -> List[str]:
    """Enabled aliases of two or more words: the ones that get their own search feeds (a one-word alias would pull in unrelated news)."""
    return [a for a in enabled_alias_texts(row) if len(a.split()) >= 2]


def seeded_exec_feed_map(db, client_id) -> Dict[str, object]:
    """{search-feed URL: executive entity id} for the client's active seeded executives (what the Run Pipeline polls for them)."""
    from app.models.entity import Entity
    from app.services.client_service import entity_search_feed_urls
    rows = seeded_rows(db, client_id, "executive")
    if not rows:
        return {}
    names = {e.id: e.name for e in db.query(Entity).filter(Entity.id.in_([r.entity_id for r in rows])).all()}
    brand_row = db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == "brand").first()
    company = brand_row.name if brand_row else next(iter(company_terms(db, client_id)), None)
    out: Dict[str, object] = {}
    for r in rows:
        name = names.get(r.entity_id)
        if name:
            for url in entity_search_feed_urls(name, co_occur_with=company, quote=True, co_quoted=True).values():
                out[url] = r.entity_id
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
    alias_urls = set()
    for r in rows:
        name = names.get(r.entity_id)
        if not name:
            continue
        co = company if r.kind == "executive" else (r.context_term or None)
        urls.update(entity_search_feed_urls(name, co_occur_with=co, quote=True, co_quoted=(r.kind == "executive")).values())
        for alias in multiword_alias_texts(r):          # alias search feeds (add-alias) are capped per run like the entity's own
            alias_urls.update(entity_search_feed_urls(alias, co_occur_with=co, quote=True, co_quoted=(r.kind == "executive")).values())
    if alias_urls:                                      # only those that exist as feeds of this client
        from app.models.rss_feed import RSSFeed
        urls |= {u for (u,) in db.query(RSSFeed.feed_url).filter(RSSFeed.client_id == client_id, RSSFeed.feed_url.in_(list(alias_urls))).all()}
    return urls
