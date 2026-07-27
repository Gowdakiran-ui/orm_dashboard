from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.schemas.document import NormalizedDocument
from app.models.document import Document
from app.utils.text_processing import canonicalize_url, generate_content_hash
from app.utils.s3_client import upload_payload
from app.services.matching_engine import engine_instance
from typing import Tuple
import structlog

logger = structlog.get_logger()

def process_and_save_document(db: Session, doc_data: NormalizedDocument) -> Tuple[bool, bool, int]:
    """
    Persists a document and finds matches.
    Returns (is_saved, is_deduplicated, match_count)
    
    Deduplication Strategy:
    - PRIMARY:   ON CONFLICT DO NOTHING on `url` (canonical URL uniqueness)
    - SECONDARY: Catch IntegrityError on `content_hash` (same content, different URL)
    Both paths are treated as successful deduplications — no crash, no retry.
    """
    canonical_url = canonicalize_url(doc_data.url)
    content_hash = generate_content_hash(doc_data.content)
    
    # Upload payload to S3 if enabled
    s3_uri = None
    from app.core.config import settings
    if settings.ENABLE_S3_STORAGE:
        try:
            s3_uri = upload_payload(content_hash, doc_data.raw_payload)
        except Exception as s3_err:
            logger.warning("s3_upload_failed_offline", error=str(s3_err), content_hash=content_hash)

    try:
        # Save Document using INSERT ON CONFLICT DO NOTHING (handles URL duplicates)
        stmt = insert(Document).values(
            url=canonical_url,
            content_hash=content_hash,
            source_id=doc_data.source_id,
            document_type=doc_data.source_type,
            title=doc_data.title,
            normalized_content=doc_data.content,
            author=doc_data.author,
            published_at=doc_data.published_at,
            collected_at=doc_data.collected_at,
            raw_storage_path=s3_uri
        ).on_conflict_do_nothing(
            index_elements=['url']
        )
        
        result = db.execute(stmt)
        db.commit()
        
        if result.rowcount == 0:
            # Document was deduplicated by URL — already existed
            logger.debug("document_deduped_by_url", url=canonical_url)
            return False, True, 0

    except IntegrityError as e:
        # Content hash conflict: same content reached us via a different URL.
        # This is a valid deduplication case, not an error.
        db.rollback()
        logger.info("document_deduped_by_content_hash", url=canonical_url, content_hash=content_hash)
        return False, True, 0
    except Exception as e:
        db.rollback()
        logger.error("document_save_failed", url=canonical_url, error=str(e))
        raise
        
    # We need the ID for the matches
    db_doc = db.query(Document).filter(Document.url == canonical_url).first()
    
    if not db_doc:
        # Race condition guard: another worker saved first between our INSERT and this SELECT
        logger.warning("document_not_found_after_insert", url=canonical_url)
        return False, True, 0
    
    # Global Matching Engine
    if not engine_instance.is_loaded:
        engine_instance.refresh_processor(db)
        
    matches = engine_instance.process_document(db, str(db_doc.id), doc_data.content)
    
    return True, False, len(matches)
