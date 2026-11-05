"""
One-time, seed-scoped rematch: matches a seeded entity's keywords against ALL existing client-visible documents and writes only
the DocumentMatch and EntityMention rows for those entities.

This is a NEW function on purpose. entity_discovery._rematch_recent_documents_for_new_entity is shared by competitor search and
looks only at documents collected in the last 6 hours; it is left as it is.

* "Visible" documents = the ones the client's pages can show: documents that carry a mention of the client's brand or product entity
  (the same co-occurrence rule documents.py uses).
* A keyword matches as a whole phrase (case and punctuation ignored) in the title or stored text. A one-word competitor name must
  also have one of its sector (context) words in the text.
* Nothing is deleted or changed; a document already matched/mentioned for the entity is skipped, so it is safe to re-run.
* No NLP is needed to score these rows: executive and benchmark scores read the DOCUMENT-level sentiment that existing documents
  already have (documents still without it are picked up by the normal pipeline), so there is no NLP batch to cap here.
  The per-entity caps (60 / 30) apply to what the backfill collects; this function only attaches what is already stored.
"""
import re
from typing import Any, Dict, Iterable, List, Optional

import structlog
from sqlalchemy import func

logger = structlog.get_logger()

BATCH = 1500


def _norm(text: Optional[str]) -> str:
    return " " + re.sub(r"[\W_]+", " ", (text or "").lower()).strip() + " "


def _phrase(term: str) -> str:
    return _norm(term)


def specs_for_entities(db, client_id, entity_ids: Iterable) -> List[Dict[str, Any]]:
    """Specs {entity_id, name, kind, terms, ctx} from the stored seeded rows and the entities' keywords."""
    from app.models.entity import Entity, EntityKeyword
    from app.models.seeded_entity import SeededEntity
    out = []
    ids = list(entity_ids)
    rows = db.query(SeededEntity).filter(SeededEntity.client_id == client_id, SeededEntity.entity_id.in_(ids),
                                         SeededEntity.status == "active").all()
    for r in rows:
        ent = db.query(Entity).filter(Entity.id == r.entity_id).first()
        kws = db.query(EntityKeyword.keyword_text).filter(EntityKeyword.entity_id == r.entity_id, EntityKeyword.is_active == True,   # noqa: E712
                                                          EntityKeyword.category.in_(("PRIMARY", "ALIAS"))).all()
        terms = {ent.name, r.name} | {k[0] for k in kws}
        out.append({"entity_id": r.entity_id, "name": ent.name, "kind": r.kind, "terms": sorted(t for t in terms if t and len(t) >= 3),
                    "ctx": [w for w in _norm(r.context_term).split() if len(w) >= 4]})
    return out


def _scan(db, client_id, specs: List[Dict[str, Any]], write: bool) -> Dict[str, Dict[str, int]]:
    from app.models.document import Document, DocumentMatch
    from app.models.entity import Entity, EntityMention
    brand_ids = [r[0] for r in db.query(Entity.id).filter(Entity.client_id == client_id, Entity.entity_type.in_(("brand", "product"))).all()]
    result = {s["name"]: {"matched_docs": 0, "already_had": 0, "new_mentions": 0, "new_matches": 0} for s in specs}
    visible = db.query(EntityMention.document_id).filter(EntityMention.entity_id.in_(brand_ids))
    total_visible = db.query(func.count(func.distinct(EntityMention.document_id))).filter(EntityMention.entity_id.in_(brand_ids)).scalar() or 0
    already_m, already_d = {}, {}
    for s in specs:
        eid = s.get("entity_id")
        already_m[s["name"]] = {r[0] for r in db.query(EntityMention.document_id).filter(EntityMention.entity_id == eid)} if eid else set()
        already_d[s["name"]] = {r[0] for r in db.query(DocumentMatch.document_id).filter(DocumentMatch.matched_entity_id == eid)} if eid else set()
    for s in specs:
        s["_phrases"] = [(t, _phrase(t)) for t in s["terms"]]
    last = None
    while True:
        q = db.query(Document.id, Document.title, Document.normalized_content).filter(Document.id.in_(visible))
        if last is not None:
            q = q.filter(Document.id > last)
        rows = q.order_by(Document.id).limit(BATCH).all()
        if not rows:
            break
        last = rows[-1][0]
        for doc_id, title, content in rows:
            text = _norm(title) + _norm(content)
            for s in specs:
                hit = next((t for t, p in s["_phrases"] if p in text), None)
                if hit is None:
                    continue
                if s["kind"] == "competitor" and len(_norm(hit).split()) < 2 and s["ctx"] and not any(w in text for w in s["ctx"]):
                    continue
                st = result[s["name"]]
                st["matched_docs"] += 1
                if doc_id in already_m[s["name"]]:
                    st["already_had"] += 1
                else:
                    st["new_mentions"] += 1
                    if write:
                        db.add(EntityMention(document_id=doc_id, entity_id=s["entity_id"], role="PERSON" if s["kind"] == "executive" else "ORG",
                                             mention_count=min(10, text.count(_phrase(hit))), confidence_score=0.9))
                if doc_id not in already_d[s["name"]]:
                    st["new_matches"] += 1
                    if write:
                        db.add(DocumentMatch(document_id=doc_id, matched_entity_id=s["entity_id"], match_type="seeded_rematch",
                                             match_confidence=0.9, matched_text=hit))
        if write:
            db.commit()
    result["_visible_documents"] = {"visible": int(total_visible)}
    return result


def rematch_seeded(db, client_id, entity_ids: Iterable) -> Dict[str, Dict[str, int]]:
    """Write DocumentMatch + EntityMention rows for the given seeded entities over all visible documents."""
    specs = specs_for_entities(db, client_id, entity_ids)
    out = _scan(db, client_id, specs, write=True)
    logger.info("seeded_rematch_done", client_id=str(client_id), **{k: v["new_mentions"] for k, v in out.items() if not k.startswith("_")})
    return out


def preview_plan(db, client_id, plan: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    """READ-ONLY: how many existing visible documents each CHOSEN seeded entity would match and how many of those it does not have yet.
    Works before anything is applied (the entity may not exist: an existing entity with the same name is used for 'already_had')."""
    from app.models.entity import Entity
    specs = []
    for key, kind, etype in (("executives", "executive", "person"), ("competitors", "competitor", "competitor")):
        for it in plan[key]:
            if not it.get("selected"):
                continue
            terms = {it["name"]} | {a["alias"] for a in it.get("aliases", []) if a.get("enabled")}
            from app.services.seeding.validator import strip_legal_words
            terms |= {strip_legal_words(t) for t in list(terms)}
            ent = db.query(Entity).filter(Entity.client_id == client_id, Entity.entity_type == etype, Entity.name.ilike(it["name"])).first()
            specs.append({"entity_id": ent.id if ent else None, "name": it["name"], "kind": kind,
                          "terms": sorted(t for t in terms if t and len(t) >= 3),
                          "ctx": [w for w in _norm(it.get("context_term")).split() if len(w) >= 4]})
    return _scan(db, client_id, specs, write=False)
