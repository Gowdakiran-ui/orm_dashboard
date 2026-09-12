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
  3. Re-runs entity matching (EntityExtractor.process_document -- the same
     code path execute_document_intelligence_sync uses for every new
     document) against the corrected content.

Deliberately NOT touched:
  - YouTube documents that already have >=1 entity_mentions row. Mutating
    their normalized_content would invalidate risk_engine.py's role-
    classification cache, which assumes document content is immutable after
    insert (see risk_engine.py's "Risk classification caching" comment) --
    safe to skip here since a document with an existing entity_mentions row
    already has that cache populated; a zero-mention document never does,
    so there is nothing to invalidate for the rows this script touches.
  - Any risk/narrative/sentiment scoring. This only re-runs the matching
    step, not a full pipeline rerun.
"""
import sys
from app.core.db import SessionLocal
from app.models.document import Document
from app.models.entity import EntityMention
from app.services.intelligence.entity_extractor import EntityExtractor
from app.services.matching_engine import engine_instance


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

        extractor = EntityExtractor()

        updated = 0
        skipped_already_prefixed = 0
        skipped_no_title = 0
        now_matched = 0
        still_unmatched = 0

        for doc in target_docs:
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

            extractor.process_document(db, str(doc.id), client_id=None)

            mention_count = db.query(EntityMention).filter(EntityMention.document_id == doc.id).count()
            if mention_count > 0:
                now_matched += 1
            else:
                still_unmatched += 1

        print(f"[backfill] normalized_content updated (title prepended): {updated}")
        print(f"[backfill] skipped, already prefixed: {skipped_already_prefixed}")
        print(f"[backfill] skipped, no title on record: {skipped_no_title}")
        print(f"[backfill] BEFORE: {before_count} unmatched -> AFTER: {now_matched} now matched, {still_unmatched} still unmatched")

    finally:
        db.close()


if __name__ == "__main__":
    main()
