"""
Attribute documents to a seeded executive because the executive's own search returned them.

A seeded executive is searched as "Name" "Company" (backfill slices and the Run Pipeline feed). Google News matches the whole article,
but only the headline and summary are stored, so a returned document often has no mention of the person in its stored text and the
normal matcher cannot link it. This module

  * records the link (document_feed_hits) whenever the search returns a document, including one already held,
  * turns a link into an EntityMention when the stored text also holds the company, the surname or a role word (gates.guard_passes).

Measured on a sample of such documents (read in full): 24 of 24 articles that could be fetched named the person. Nothing here changes
a formula or a weight; it only decides which documents are evidence for the executive, in the same way the seeded gate already does.
All writes are idempotent.
"""
import datetime as dt
from typing import Any, Dict, Iterable, List, Optional

import structlog

from app.services.seeding import gates

logger = structlog.get_logger()

ATTRIBUTED_CONFIDENCE = 0.6          # lower than a matcher mention (0.9): the name is in the article, not in the stored text


def _insert_ignore(db, rows: List[Dict[str, Any]]) -> None:
    from app.models.document_feed_hit import DocumentFeedHit
    if not rows:
        return
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(DocumentFeedHit).values(rows).on_conflict_do_nothing(index_elements=["document_id", "entity_id"]))


def find_document_id(db, url: Optional[str], content: Optional[str] = None):
    """The held document for a search result: by canonical URL, else by the headline hash (the same two keys the save dedups on)."""
    from app.models.document import Document
    from app.utils.text_processing import canonicalize_url, generate_content_hash
    if url:
        row = db.query(Document.id).filter(Document.url == canonicalize_url(url)).first()
        if row:
            return row[0]
    if content:
        h = generate_content_hash(content)
        if h:
            row = db.query(Document.id).filter(Document.content_hash == h).first()
            if row:
                return row[0]
    return None


def record_hit(db, client_id, entity_id, document_id, source: str, query: Optional[str] = None) -> None:
    """Record that this executive's search returned this document. Never raises into the caller's collection loop."""
    if document_id is None or not gates.hits_table_exists(db):
        return
    try:
        _insert_ignore(db, [dict(document_id=document_id, client_id=client_id, entity_id=entity_id, source=source[:30],
                                 query=(query or None), seen_at=dt.datetime.now(dt.timezone.utc))])
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("feed_hit_record_failed", error=str(e)[:200])


def record_hit_for_item(db, client_id, entity_id, norm: Dict[str, Any], source: str, query: Optional[str] = None) -> bool:
    """Look the saved/deduped document up by the normalised item and record the hit. True when a document was found."""
    doc_id = find_document_id(db, norm.get("url"), norm.get("content"))
    if doc_id is None:
        return False
    record_hit(db, client_id, entity_id, doc_id, source, query)
    return True


def attribute_hits(db, client_id, entity_ids: Optional[Iterable] = None, write: bool = True) -> Dict[str, Dict[str, int]]:
    """For the client's active seeded executives: add an EntityMention for every hit document that has none yet and passes the guard.
    Returns {name: {hits, already_mentioned, attributed, blocked_by_guard}}. write=False only counts. With SEEDED_COUNT_SEARCH_HITS off (the
    default) nothing is written, whatever `write` says: the counts still show what turning it on would attribute."""
    from sqlalchemy import func
    from app.models.document import Document
    from app.models.document_feed_hit import DocumentFeedHit
    from app.models.entity import Entity, EntityMention
    out: Dict[str, Dict[str, int]] = {}
    if not gates.hits_table_exists(db):
        return out
    write = write and gates.count_hits_enabled()
    wanted = set(entity_ids) if entity_ids is not None else None
    co = gates.company_terms(db, client_id)
    for r in gates.seeded_rows(db, client_id, "executive"):
        if wanted is not None and r.entity_id not in wanted:
            continue
        ent = db.query(Entity).filter(Entity.id == r.entity_id).first()
        name = ent.name if ent else r.name
        rows = db.query(Document.id, Document.title, func.substr(Document.normalized_content, 1, gates.LEAD_CHARS)).join(
            DocumentFeedHit, DocumentFeedHit.document_id == Document.id).filter(DocumentFeedHit.entity_id == r.entity_id).all()
        have = {m[0] for m in db.query(EntityMention.document_id).filter(EntityMention.entity_id == r.entity_id).all()}
        st = {"hits": len(rows), "already_mentioned": 0, "attributed": 0, "blocked_by_guard": 0}
        for doc_id, title, lead in rows:
            if doc_id in have:
                st["already_mentioned"] += 1
            elif not gates.guard_passes(title, lead, co, name):
                st["blocked_by_guard"] += 1
            else:
                st["attributed"] += 1
                if write:
                    db.add(EntityMention(document_id=doc_id, entity_id=r.entity_id, role="PERSON", mention_count=1,
                                         confidence_score=ATTRIBUTED_CONFIDENCE))
        if write and st["attributed"]:
            db.commit()
        out[name] = st
    if write:
        logger.info("feed_hits_attributed", client_id=str(client_id), **{k.replace(" ", "_"): v["attributed"] for k, v in out.items()})
    return out


def link_existing(db, client_id, fetch=None, months: int = 24, step: int = 1, today: Optional[dt.date] = None,
                  adapter=None) -> Dict[str, Dict[str, int]]:
    """One-off, retroactive: for each active seeded executive, run the "Name" "Company" Google News search over the last `months`
    months in `step`-month slices (free requests) and record a hit for every result that is ALREADY HELD. Saves no document,
    starts no NLP. Returns {name: {items, held, linked}}. Run attribute_hits afterwards to turn the links into mentions."""
    from app.models.entity import Entity
    from app.services.backfill import slicing
    if adapter is None:
        from app.adapters.rss import RSSAdapter
        adapter = RSSAdapter()
    if fetch is None:
        from app.services.backfill.fetchers import fetch_google_news
        fetch = lambda q, a, b: fetch_google_news(q, a, b, {})          # noqa: E731
    end = (today or dt.datetime.now(dt.timezone.utc).date()) + dt.timedelta(days=1)
    start = end - dt.timedelta(days=30 * months)
    brand = db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == "brand").first()
    company = brand.name if brand else None
    out: Dict[str, Dict[str, int]] = {}
    if not company:
        return out
    for r in gates.seeded_rows(db, client_id, "executive"):
        ent = db.query(Entity).filter(Entity.id == r.entity_id).first()
        name = ent.name if ent else r.name
        query = '"%s" "%s"' % (name.replace('"', " ").strip(), company.replace('"', " ").strip())
        st = {"items": 0, "held": 0, "linked": 0}
        seen = set()
        for a, b in slicing.calendar_slices(start, end, step):
            for raw in fetch(query, a, b):
                try:
                    norm = adapter.normalize(raw, "00000000-0000-0000-0000-000000000000")
                except Exception:
                    continue
                key = norm.get("url")
                if not key or key in seen:
                    continue
                seen.add(key)
                st["items"] += 1
                doc_id = find_document_id(db, norm.get("url"), norm.get("content"))
                if doc_id is not None:
                    st["held"] += 1
                    record_hit(db, client_id, r.entity_id, doc_id, "google_news", query)
                    st["linked"] += 1
        out[name] = st
    return out
