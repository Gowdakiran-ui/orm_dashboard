"""
Part D Fix 3 -- one-off backfill for the title-inclusive YouTube entity
matching fix (adapters/youtube.py's normalize(), Fix 1).

Scope, deliberately narrow (per the task): this is a genuine bug that wrongly
excluded real, legitimate content, unlike the deliberate going-forward-only
noise-reduction gates elsewhere in this project (reach_trust_config.py).
Existing YouTube documents were saved with normalized_content built only
from the video description, never the title -- documents whose brand name
only appeared in the title got zero entity_mentions and are invisible to
every client. This script:

  1. Finds YouTube documents with zero entity_mentions rows.
  2. Prepends title to normalized_content for exactly those rows (skipped if
     already prepended, so this is safe to re-run).
  3. Re-runs ONLY the keyword-matching step (Step 1 of
     entity_extractor.py's EntityExtractor.process_document -- find_matches +
     evaluate_match_accuracy + write EntityMention) against the corrected
     content.

Deliberately does NOT call EntityExtractor.process_document directly, which
would also run its Step 2 (NER-based entity_discovery, candidate
executive/competitor creation). Two reasons:
  - Scope: the task asked for a targeted re-match pass only, not new
    discovery side effects, on documents that are up to 5 months old.
  - A real bug this backfill surfaced live: entity_discovery.py's candidate
    insert path does a plain INSERT with no ON CONFLICT guard, and running
    discovery across ~190 historical documents at once hit a real duplicate
    ((client_id, name) already existed from an earlier, different document)
    and crashed with psycopg2.errors.UniqueViolation. That is a pre-existing
    bug in entity_discovery.py, unrelated to this fix -- logged separately,
    not fixed here -- and this script avoids ever exercising that path.

Deliberately NOT touched:
  - YouTube documents that already have >=1 entity_mentions row. Mutating
    their normalized_content would invalidate risk_engine.py's role-
    classification cache, which assumes document content is immutable after
    insert (see risk_engine.py's "Risk classification caching" comment) --
    safe to skip here since a document with an existing entity_mentions row
    already has that cache populated; a zero-mention document never does,
    so there is nothing to invalidate for the rows this script touches.
  - Any risk/narrative/sentiment scoring, and no entity_discovery candidates.
    This only re-runs the matching step, not a full pipeline rerun.

Per-document isolation: one document's failure (matches process_document's
own guarantee elsewhere in this codebase, e.g.
entity_matching_batch_processor.py) never stops the batch -- each document
commits or rolls back independently.
"""
import traceback

from app.core.db import SessionLocal
from app.models.document import Document
from app.models.entity import Entity, EntityMention
from app.services.matching_engine import engine_instance, get_client_boost_terms


def match_one_document(db, document) -> int:
    """
    Inline copy of entity_extractor.py's Step 1 only (matching, no
    discovery). Returns the number of accepted EntityMention rows written.
    """
    matches = engine_instance.find_matches(document.normalized_content)

    db.query(EntityMention).filter(EntityMention.document_id == document.id).delete()

    unique_entities = set()
    boost_terms_by_client = {}
    written = 0

    for m in matches:
        entity_id = m["entity_id"]
        if entity_id in unique_entities:
            continue
        unique_entities.add(entity_id)

        entity = db.query(Entity).filter(Entity.id == entity_id).first()
        if not entity:
            continue

        if entity.client_id not in boost_terms_by_client:
            boost_terms_by_client[entity.client_id] = get_client_boost_terms(db, entity.client_id)
        boost_terms = boost_terms_by_client[entity.client_id]

        accuracy_meta = engine_instance.evaluate_match_accuracy(
            document.normalized_content, m, entity.domain, entity.name,
            executive_terms=boost_terms["executive_terms"],
            product_terms=boost_terms["product_terms"],
            entity_industry=entity.industry,
        )

        if accuracy_meta["status"] == "accepted":
            mention = EntityMention(
                document_id=document.id,
                entity_id=entity.id,
                role="ORG" if entity.entity_type in ["brand", "competitor", "product", "rejected_competitor"] else "PERSON",
                mention_count=1,
                confidence_score=accuracy_meta["final_confidence"],
            )
            db.add(mention)
            written += 1

    return written


def main():
    db = SessionLocal()
    try:
        matched_doc_ids = db.query(EntityMention.document_id).distinct().scalar_subquery()
        target_docs = (
            db.query(Document)
            .filter(Document.document_type == "youtube")
            .filter(~Document.id.in_(matched_doc_ids))
            .all()
        )

        before_count = len(target_docs)
        print(f"[backfill] {before_count} YouTube documents with zero entity_mentions found")

        if not engine_instance.is_loaded:
            engine_instance.refresh_processor(db)

        updated = 0
        skipped_already_prefixed = 0
        skipped_no_title = 0
        now_matched = 0
        still_unmatched = 0
        errors = 0

        for doc in target_docs:
            doc_id = doc.id
            try:
                title = (doc.title or "").strip()
                content = doc.normalized_content or ""

                if not title:
                    skipped_no_title += 1
                elif content.startswith(title):
                    skipped_already_prefixed += 1
                else:
                    doc.normalized_content = f"{title}\n\n{content}" if content else title
                    db.commit()
                    updated += 1

                written = match_one_document(db, doc)
                db.commit()

                if written > 0:
                    now_matched += 1
                else:
                    still_unmatched += 1

            except Exception as exc:
                db.rollback()
                errors += 1
                print(f"[backfill] ERROR document_id={doc_id}: {exc}")
                traceback.print_exc()

        print(f"[backfill] normalized_content updated (title prepended): {updated}")
        print(f"[backfill] skipped, already prefixed: {skipped_already_prefixed}")
        print(f"[backfill] skipped, no title on record: {skipped_no_title}")
        print(f"[backfill] errors (isolated, batch continued): {errors}")
        print(f"[backfill] BEFORE: {before_count} unmatched -> AFTER: {now_matched} now matched, {still_unmatched} still unmatched")

    finally:
        db.close()


if __name__ == "__main__":
    main()
