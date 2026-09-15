"""
One-off backfill for the entity_mentions-without-document_matches gap.

Root cause (confirmed by tracing both write paths, not assumed from the
symptom): entity_mentions and document_matches are written by two entirely
independent functions that both consume matching_engine.py's find_matches()
but never call each other:

  - entity_extractor.py::EntityExtractor.process_document() writes
    EntityMention (its "Step 1"), then runs entity_discovery_engine's
    NER-based candidate discovery (its "Step 2"). Never writes
    DocumentMatch.
  - matching_engine.py::process_document() is the sole writer of
    DocumentMatch -- pure FlashText keyword matching gated by
    should_write_document_match() (the brand co-occurrence gate). Never
    touches entity_discovery or NER in any way.

scripts/backfill_youtube_title_match.py (a prior one-off fix) deliberately
avoided calling EntityExtractor.process_document() to avoid triggering
entity_discovery's NER/candidate-creation side effects on old content --
a documented, still-valid scope decision. But it never wrote
DocumentMatch either, and its docstring never mentions that table: the gap
this script closes was simply out of that backfill's scope, not a
preserved deliberate tradeoff. matching_engine.py::process_document() does
not run entity_discovery, so none of that prior concern applies here.

Scope: only the (document, client) pairs confirmed to have a brand/product
entity_mentions row but zero document_matches rows for that client. Does
NOT re-run entity_extractor.py or entity_discovery.py. Does NOT bypass
should_write_document_match()'s brand co-occurrence gate -- that gate is
applied exactly as it is at live ingestion time.

document_matches has no unique constraint on (document_id,
matched_entity_id) -- only a PK on id (confirmed in schema.sql). Some of
the target documents already carry document_matches rows for OTHER
clients (this script's target query is scoped per-client-absence, not
"zero document_matches for this document at all"), so a blind re-run
risks duplicate rows for an entity that already matched. This script
explicitly checks existing document_matches per document first and skips
any entity_id already present.

Per-document isolation: one document's failure never stops the batch --
same convention as backfill_youtube_title_match.py and
entity_matching_batch_processor.py.
"""
import traceback

from sqlalchemy import text

from app.core.db import SessionLocal
from app.models.document import Document, DocumentMatch
from app.services.matching_engine import engine_instance, should_write_document_match


def backfill_one_document(db, document_id) -> int:
    """Returns the number of DocumentMatch rows written for this document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc or not doc.normalized_content:
        return 0

    existing_entity_ids = {
        row[0] for row in db.execute(
            text("SELECT matched_entity_id FROM document_matches WHERE document_id = :did"),
            {"did": str(document_id)},
        ).fetchall()
    }

    matches = engine_instance.find_matches(doc.normalized_content)
    doc_text_lower = doc.normalized_content.lower()
    boost_terms_cache = {}

    unique_entities = set()
    written = 0
    for m in matches:
        entity_id = m["entity_id"]
        if entity_id in unique_entities:
            continue
        unique_entities.add(entity_id)

        if entity_id in existing_entity_ids:
            continue

        if not should_write_document_match(db, m["client_id"], doc_text_lower, boost_terms_cache):
            continue

        db.add(DocumentMatch(
            document_id=document_id,
            matched_entity_id=entity_id,
            match_type=m["match_type"],
            match_confidence=m["confidence"],
            matched_text=m.get("matched_keyword", "[Hidden/Aggregated]"),
        ))
        written += 1

    return written


def main():
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT DISTINCT em.document_id, e.client_id
            FROM entity_mentions em
            JOIN entities e ON e.id = em.entity_id
            WHERE e.entity_type IN ('brand', 'product')
            AND NOT EXISTS (
                SELECT 1 FROM document_matches dm
                LEFT JOIN entities me ON me.id = dm.matched_entity_id
                WHERE dm.document_id = em.document_id
                AND (me.client_id = e.client_id OR dm.matched_entity_id IS NULL)
            )
        """)).fetchall()

        doc_ids = sorted({r[0] for r in rows})
        print(f"[docmatch-backfill] {len(rows)} (document, client) gap pairs across {len(doc_ids)} documents")

        if not engine_instance.is_loaded:
            engine_instance.refresh_processor(db)

        total_written = 0
        docs_with_writes = 0
        docs_with_no_writes = 0
        errors = 0

        for doc_id in doc_ids:
            try:
                written = backfill_one_document(db, doc_id)
                db.commit()
                if written > 0:
                    total_written += written
                    docs_with_writes += 1
                else:
                    docs_with_no_writes += 1
            except Exception as exc:
                db.rollback()
                errors += 1
                print(f"[docmatch-backfill] ERROR document_id={doc_id}: {exc}")
                traceback.print_exc()

        print(f"[docmatch-backfill] DocumentMatch rows written: {total_written}")
        print(f"[docmatch-backfill] documents with >=1 row written: {docs_with_writes}")
        print(f"[docmatch-backfill] documents with 0 rows written (gate-filtered or already covered): {docs_with_no_writes}")
        print(f"[docmatch-backfill] errors (isolated, batch continued): {errors}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
