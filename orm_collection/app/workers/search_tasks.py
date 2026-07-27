from celery import shared_task
from app.core.db import SessionLocal
from app.models.entity import EntityKeyword
from app.models.search import SearchSourceConfiguration, SearchCursor, SearchJob
from app.adapters.reddit import RedditAdapter
from app.adapters.youtube import YouTubeAdapter
from app.workers.document_processor import process_document_task
from datetime import datetime, timezone, timedelta
import json

@shared_task(bind=True, max_retries=3)
def schedule_searches(self):
    """
    Celery Beat task to schedule searches based on keyword search_frequency_minutes.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        active_sources = db.query(SearchSourceConfiguration).filter(SearchSourceConfiguration.enabled == True).all()
        active_keywords = db.query(EntityKeyword).filter(EntityKeyword.is_active == True).all()
        
        for source in active_sources:
            for kw in active_keywords:
                # Check when it was last searched
                cursor = db.query(SearchCursor).filter(
                    SearchCursor.keyword_id == kw.id,
                    SearchCursor.source_type == source.source_type
                ).first()
                
                needs_search = False
                if not cursor or not cursor.last_searched_at:
                    needs_search = True
                else:
                    elapsed = (now - cursor.last_searched_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
                    if elapsed >= kw.search_frequency_minutes:
                        needs_search = True
                        
                if needs_search:
                    # Enqueue task
                    execute_search_task.delay(source.source_type, kw.keyword_text, str(kw.id))
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()

@shared_task(bind=True, max_retries=3)
def execute_search_task(self, source_type: str, keyword: str, keyword_id: str):
    db = SessionLocal()
    try:
        source_config = db.query(SearchSourceConfiguration).filter(SearchSourceConfiguration.source_type == source_type).first()
        if not source_config or not source_config.enabled:
            return
            
        cursor = db.query(SearchCursor).filter(
            SearchCursor.keyword_id == keyword_id,
            SearchCursor.source_type == source_type
        ).first()
        
        cursor_val = cursor.cursor_value if cursor else None
        
        # Instantiate Adapter
        adapter = None
        if source_type == 'reddit':
            adapter = RedditAdapter()
        elif source_type == 'youtube':
            adapter = YouTubeAdapter()
        else:
            return
            
        # Create Job
        job = SearchJob(source_type=source_type, keyword=keyword, status="processing")
        db.add(job)
        db.commit()
        db.refresh(job)
        
        raw_results, new_cursor_val = adapter.search(keyword, cursor=cursor_val, limit=25)
        
        for res in raw_results:
            normalized_doc = adapter.normalize(res, str(source_config.id))
            raw_payload = json.dumps(res)
            # Enqueue to Document Processor
            # document_processor handles standard normalization mapping
            # Wait, the document_processor expects raw_payload and calls adapter.normalize
            # But process_document_task expects source_id (which here is the SearchSourceConfiguration id or a dummy)
            # We need to adapt `process_document_task` to handle search results, or just use it.
            # But `process_document_task` hardcodes `RSSAdapter()`. We need to fix that or bypass it.
            # Since `process_document_task` hardcoded `RSSAdapter`, we can instead just call `process_and_save_document` directly here 
            # OR pass the adapter type to `process_document_task`.
            
            # Let's call process_and_save_document directly for milestone 4, or ideally we'd pass source_type to document_processor.
            # For simplicity, we just save here as we already normalized it!
            from app.services.document_service import process_and_save_document
            from app.schemas.document import NormalizedDocument
            
            try:
                norm_doc = NormalizedDocument(**normalized_doc)
                is_saved, is_dedup, match_count = process_and_save_document(db, norm_doc)
                if is_saved: job.results_saved += 1
                if match_count > 0: job.results_matched += 1
            except Exception as e:
                import structlog
                import traceback
                logger = structlog.get_logger()
                logger.error(
                    "search_document_processing_failed",
                    task="execute_search_task",
                    document=normalized_doc,
                    url=normalized_doc.get("url"),
                    client="N/A",
                    exception_type=type(e).__name__,
                    stack_trace=traceback.format_exc(),
                    processing_stage="normalization_and_save"
                )
                
        job.results_found = len(raw_results)
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        
        if not cursor:
            cursor = SearchCursor(keyword_id=keyword_id, source_type=source_type)
            db.add(cursor)
            
        cursor.cursor_value = new_cursor_val
        cursor.last_searched_at = datetime.now(timezone.utc)
        
        db.commit()
        
    except Exception as exc:
        db.rollback()
        backoff = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=backoff)
    finally:
        db.close()
