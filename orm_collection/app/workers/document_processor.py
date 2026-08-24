from celery import shared_task
from app.core.db import SessionLocal
from app.models.collection_job import CollectionJob
from app.adapters.rss import RSSAdapter
from app.adapters.registry import ADAPTER_REGISTRY
from app.schemas.document import NormalizedDocument
from app.services.document_service import process_and_save_document
import json
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()

@shared_task(bind=True, max_retries=3)
def process_document_task(self, job_id: str, source_id: str, raw_document_data_json: str, extract_article: bool = False, client_id: str = None, source_format: str = "rss"):
    db = SessionLocal()
    try:
        raw_data = json.loads(raw_document_data_json)

        if extract_article:
            # Placeholder for Article Extraction (e.g. using beautifulsoup4 or newspaper3k)
            # url = raw_data.get('link')
            # html = requests.get(url).text
            # raw_data['content'] = extract_text(html)
            pass

        adapter_cls = ADAPTER_REGISTRY.get(source_format, RSSAdapter)
        adapter = adapter_cls()
        normalized_dict = adapter.normalize(raw_data, source_id)
        normalized_doc = NormalizedDocument(**normalized_dict)

        is_saved, is_dedup, match_count = process_and_save_document(db, normalized_doc)

        if is_saved:
            from app.models.document import Document
            from app.utils.text_processing import canonicalize_url
            canonical_url = canonicalize_url(normalized_doc.url)
            db_doc = db.query(Document).filter(Document.url == canonical_url).first()
            if db_doc:
                from app.workers.intelligence_tasks import process_document_intelligence
                process_document_intelligence.delay(str(db_doc.id), client_id=client_id, job_id=job_id)

        # Update Job Metrics
        job = db.query(CollectionJob).filter(CollectionJob.job_id == job_id).first()
        if job:
            if is_saved:
                job.documents_saved += 1
            if is_dedup:
                job.documents_deduplicated += 1
            if match_count > 0:
                job.documents_matched += match_count
            db.commit()
            
            # If the document was not saved (i.e. deduplicated or skipped), it is finished now
            if not is_saved:
                from app.utils.redis_client import redis_client
                processed_key = f"pipeline:job:processed:{job_id}"
                total_key = f"pipeline:job:total:{job_id}"
                new_val = redis_client.incrby(processed_key)
                total_raw = redis_client.get(total_key)
                if total_raw and new_val >= int(total_raw):
                    from app.workers.collection_tasks import check_and_update_job_status
                    check_and_update_job_status(db, job_id)
        else:
            logger.warning("collection_job_not_found", job_id=job_id)
            
    except Exception as exc:
        db.rollback()
        if self.request.retries < self.max_retries:
            # Retry/backoff pattern 1 of 4 in this codebase: Celery exponential
            # backoff (FINDINGS.md #18). The other 3: flat Celery countdown
            # (intelligence_tasks.py, aggregation_tasks.py), in-process retry
            # classes (RetryConfig/SentimentRetryConfig/TopicRetryConfig), and
            # evaluate_alerts's own transient-error-conditional pattern
            # (aggregation_tasks.py). Intentional per-task variance, not drift
            # -- not consolidated this phase (see FINDINGS.md for why).
            backoff = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=backoff)
            
        job = db.query(CollectionJob).filter(CollectionJob.job_id == job_id).first()
        if job:
            job.documents_failed += 1
            db.commit()
            
            from app.utils.redis_client import redis_client
            processed_key = f"pipeline:job:processed:{job_id}"
            total_key = f"pipeline:job:total:{job_id}"
            new_val = redis_client.incrby(processed_key)
            total_raw = redis_client.get(total_key)
            if total_raw and new_val >= int(total_raw):
                from app.workers.collection_tasks import check_and_update_job_status
                check_and_update_job_status(db, job_id)
        raise exc
    finally:
        db.close()
