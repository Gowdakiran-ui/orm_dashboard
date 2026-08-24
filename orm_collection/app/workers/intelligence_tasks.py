from celery import shared_task
from app.core.db import SessionLocal
from app.services.intelligence.topic_classifier import TopicClassifier
from app.services.intelligence.topic_classification_batch_processor import HardenedTopicClassifier, TopicRetryConfig, logger as topic_batch_logger
from app.services.intelligence.entity_extractor import EntityExtractor
from app.services.intelligence.sentiment_analyzer import SentimentAnalyzer
from app.services.intelligence.entity_discovery import entity_discovery_engine
import structlog
import uuid
from datetime import datetime, timezone, timedelta

logger = structlog.get_logger()

# Initialize models globally for the worker process to avoid reloading per task
raw_topic_classifier = TopicClassifier(use_mock=False)
hardened_topic_classifier = HardenedTopicClassifier(
    classifier_instance=raw_topic_classifier,
    retry_config=TopicRetryConfig(max_retries=2, base_backoff_seconds=0.1)
)
entity_extractor = EntityExtractor()
sentiment_analyzer = SentimentAnalyzer(use_mock=False)

def execute_document_intelligence_sync(document_id: str, client_id: str = None, celery_task=None):
    import time
    t0 = time.perf_counter()
    logger.info("pipeline_stage_started", stage="process_document_intelligence", document_id=document_id, client_id=client_id)

    # Retrieve client_id for logging if possible
    db = SessionLocal()
    try:
        from app.models.document import Document
        # Row lock (matches the pattern already used for client-row locking in
        # aggregation_tasks.py and document locking in topic_classification_batch_processor.py):
        # without it, two workers reading the same document's status before either
        # commits would both pass the check and both proceed into the pipeline.
        doc = db.query(Document).filter(Document.id == document_id).with_for_update().first()
        if doc:
            if doc.processing_status in ["MATCHED", "SKIPPED", "FAILED"]:
                logger.info("document_already_processed_skipping", document_id=document_id)
                return
            doc.processing_status = "PROCESSING"
            doc.processing_started_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        logger.error("failed_to_fetch_document", error=str(exc))
    finally:
        db.close()

    # 1. Phase 1A: Entity Matching (Atomic Transaction)
    entity_db = SessionLocal()
    discovery_results_list = []
    t_matching = time.perf_counter()
    try:
        extraction_result = entity_extractor.process_document(entity_db, document_id, client_id)
        if extraction_result:
            matched_client_ids, discovery_results_list = extraction_result
        else:
            matched_client_ids, discovery_results_list = [], []
        entity_db.commit()
    except Exception as exc:
        entity_db.rollback()
        logger.error("entity_extraction_failed_rolling_back", document_id=document_id, error=str(exc))
        try:
            from app.models.document import Document
            doc = entity_db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.processing_status = "FAILED"
                entity_db.commit()
        except Exception as e:
            logger.error("failed_to_set_failed_status", error=str(e))
        entity_db.close()
        if celery_task:
            # Retry/backoff pattern 2 of 4 in this codebase: Celery flat
            # countdown (FINDINGS.md #18) -- same delay regardless of retry
            # count, unlike document_processor.py/collection_tasks.py's
            # exponential backoff. The other 2 patterns: in-process retry
            # classes (RetryConfig/SentimentRetryConfig/TopicRetryConfig) and
            # evaluate_alerts's transient-error-conditional retry
            # (aggregation_tasks.py). Intentional per-task variance, not
            # drift -- not consolidated this phase.
            raise celery_task.retry(exc=exc, countdown=60)
        else:
            raise exc
    finally:
        entity_db.close()
    duration_matching = (time.perf_counter() - t_matching) * 1000
    print(f"[TIMING] document_id={document_id} stage=entity_matching duration_ms={duration_matching:.2f}", flush=True)

    # 2. Phase 1B: Topic Classification
    # Uses _process_with_retry (not process_batch) so the classifier's own
    # transient/permanent retry-with-backoff machinery actually runs instead
    # of being dead code -- see FINDINGS.md #23. Stage isolation (a topic
    # failure must never abort entity extraction/sentiment/the pipeline) is
    # preserved: exceptions are still only caught and logged here, never
    # re-raised.
    t_topic = time.perf_counter()
    try:
        from app.models.document import Document as _TopicDoc
        topic_run_id = uuid.uuid4().hex
        topic_batch_id = uuid.uuid4().hex[:12]
        topic_retry_db = SessionLocal()
        try:
            topic_doc = topic_retry_db.query(_TopicDoc).filter(_TopicDoc.id == document_id).first()
            topic_retry_count = topic_doc.topic_retry_count if topic_doc else 0
        finally:
            topic_retry_db.close()

        topic_doc_logger = topic_batch_logger.bind(
            run_id=topic_run_id,
            batch_id=topic_batch_id,
            client_id=client_id,
            worker_id=hardened_topic_classifier.worker_id,
            document_id=document_id
        )
        hardened_topic_classifier._process_with_retry(
            document_id=document_id,
            run_id=topic_run_id,
            batch_id=topic_batch_id,
            client_id=client_id,
            current_retry_count=topic_retry_count,
            doc_logger=topic_doc_logger
        )
    except Exception as topic_exc:
        logger.error("topic_classification_failed_stage_isolated", document_id=document_id, error=str(topic_exc))
    duration_topic = (time.perf_counter() - t_topic) * 1000
    print(f"[TIMING] document_id={document_id} stage=topic_classification duration_ms={duration_topic:.2f}", flush=True)

    # 3. Phase 1C: Sentiment Analysis
    # Same _process_with_retry wiring as topic classification above.
    t_sentiment = time.perf_counter()
    try:
        from app.services.intelligence.sentiment_batch_processor import HardenedSentimentProcessor, logger as sentiment_batch_logger
        from app.models.document import Document as _SentDoc
        hardened_sentiment = HardenedSentimentProcessor(analyzer_instance=sentiment_analyzer)

        sentiment_run_id = uuid.uuid4().hex
        sentiment_batch_id = uuid.uuid4().hex[:12]
        sentiment_retry_db = SessionLocal()
        try:
            sentiment_doc = sentiment_retry_db.query(_SentDoc).filter(_SentDoc.id == document_id).first()
            sentiment_retry_count = sentiment_doc.sentiment_retry_count if sentiment_doc else 0
        finally:
            sentiment_retry_db.close()

        sentiment_doc_logger = sentiment_batch_logger.bind(
            run_id=sentiment_run_id,
            batch_id=sentiment_batch_id,
            client_id=client_id,
            worker_id=hardened_sentiment.worker_id,
            document_id=document_id
        )
        hardened_sentiment._process_with_retry(
            document_id=document_id,
            run_id=sentiment_run_id,
            batch_id=sentiment_batch_id,
            client_id=client_id,
            current_retry_count=sentiment_retry_count,
            doc_logger=sentiment_doc_logger
        )
    except Exception as sent_exc:
        logger.error("sentiment_analysis_failed_stage_isolated", document_id=document_id, error=str(sent_exc))
    duration_sentiment = (time.perf_counter() - t_sentiment) * 1000
    print(f"[TIMING] document_id={document_id} stage=sentiment_analysis duration_ms={duration_sentiment:.2f}", flush=True)

    # 4. Phase 1D: Executive and Competitor Candidate Promotion
    t_promo = time.perf_counter()
    try:
        promotion_db = SessionLocal()
        try:
            for cid in matched_client_ids:
                promotion_result = entity_discovery_engine.promote_executive_candidates(promotion_db, str(cid))
                if promotion_result.get("promoted_count", 0) > 0:
                    logger.info(
                        "executive_candidates_promoted",
                        client_id=str(cid),
                        promoted_count=promotion_result["promoted_count"],
                        promoted_executives=promotion_result.get("promoted_executives", [])
                    )
                
                comp_promo_result = entity_discovery_engine.promote_competitor_candidates(promotion_db, str(cid))
                if comp_promo_result.get("promoted_count", 0) > 0:
                    logger.info(
                        "competitor_candidates_promoted",
                        client_id=str(cid),
                        promoted_count=comp_promo_result["promoted_count"]
                    )
            promotion_db.commit()
        except Exception as promo_exc:
            promotion_db.rollback()
            logger.error("candidate_promotion_failed_stage_isolated", document_id=document_id, error=str(promo_exc))
        finally:
            promotion_db.close()
    except Exception as exc:
        logger.error("candidate_promotion_failed", document_id=document_id, error=str(exc))
    duration_promo = (time.perf_counter() - t_promo) * 1000
    print(f"[TIMING] document_id={document_id} stage=candidate_promotion duration_ms={duration_promo:.2f}", flush=True)

    # 5. Phase 1E: Persistence Validation & Verification
    t_verify = time.perf_counter()
    for cid in matched_client_ids:
        verify_db = SessionLocal()
        try:
            from app.models.document import Document
            from app.models.entity import EntityMention, Entity
            from app.models.executive_candidate import ExecutiveCandidate
            from app.models.competitor_candidate import CompetitorCandidate
            from app.models.executive_reputation import ExecutiveReputationScore
            from app.models.competitor_benchmark import CompetitorBenchmark
            
            doc_count = verify_db.query(Document).count()
            em_count = verify_db.query(EntityMention).join(Entity).filter(Entity.client_id == str(cid)).count()
            exec_cand_count = verify_db.query(ExecutiveCandidate).filter(ExecutiveCandidate.client_id == str(cid)).count()
            comp_cand_count = verify_db.query(CompetitorCandidate).filter(CompetitorCandidate.client_id == str(cid)).count()
            person_count = verify_db.query(Entity).filter(Entity.client_id == str(cid), Entity.entity_type == 'person').count()
            competitor_count = verify_db.query(Entity).filter(Entity.client_id == str(cid), Entity.entity_type == 'competitor').count()
            rep_count = verify_db.query(ExecutiveReputationScore).filter(ExecutiveReputationScore.client_id == str(cid)).count()
            bench_count = verify_db.query(CompetitorBenchmark).filter(CompetitorBenchmark.client_id == str(cid)).count()
            
            expected_exec_created = 0
            expected_comp_created = 0
            for res in discovery_results_list:
                if res.get("client_id") == str(cid):
                    expected_exec_created = res.get("executive_candidates_created", 0)
                    expected_comp_created = res.get("competitor_candidates_created", 0)
                    break
                    
            logger.info(
                "pipeline_verification_complete",
                client_id=str(cid),
                documents=doc_count,
                entity_mentions=em_count,
                executive_candidates=exec_cand_count,
                competitor_candidates=comp_cand_count,
                person_entities=person_count,
                competitor_entities=competitor_count,
                executive_reputation_scores=rep_count,
                competitor_benchmarks=bench_count,
                expected_exec_candidates_created=expected_exec_created,
                expected_comp_candidates_created=expected_comp_created
            )
        except Exception as v_exc:
            logger.error("pipeline_verification_failed", client_id=str(cid), error=str(v_exc))
        finally:
            verify_db.close()
    duration_verify = (time.perf_counter() - t_verify) * 1000
    print(f"[TIMING] document_id={document_id} stage=persistence_verification duration_ms={duration_verify:.2f}", flush=True)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"[TIMING] document_id={document_id} stage=total_document_intelligence duration_ms={elapsed_ms:.2f}", flush=True)


@shared_task(bind=True, max_retries=3, queue="nlp_queue")
def process_document_intelligence(self, document_id: str, client_id: str = None, job_id: str = None):
    try:
        execute_document_intelligence_sync(document_id, client_id=client_id, celery_task=self)
        if job_id:
            from app.utils.redis_client import redis_client
            from app.core.db import SessionLocal
            db = SessionLocal()
            try:
                processed_key = f"pipeline:job:processed:{job_id}"
                total_key = f"pipeline:job:total:{job_id}"
                new_val = redis_client.incrby(processed_key)
                total_raw = redis_client.get(total_key)
                if total_raw and new_val >= int(total_raw):
                    from app.workers.collection_tasks import check_and_update_job_status
                    check_and_update_job_status(db, job_id)
            finally:
                db.close()
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)
            
        if job_id:
            from app.utils.redis_client import redis_client
            from app.core.db import SessionLocal
            from app.models.collection_job import CollectionJob
            db = SessionLocal()
            try:
                job = db.query(CollectionJob).filter(CollectionJob.job_id == job_id).first()
                if job:
                    job.documents_failed += 1
                    db.commit()
                processed_key = f"pipeline:job:processed:{job_id}"
                total_key = f"pipeline:job:total:{job_id}"
                new_val = redis_client.incrby(processed_key)
                total_raw = redis_client.get(total_key)
                if total_raw and new_val >= int(total_raw):
                    from app.workers.collection_tasks import check_and_update_job_status
                    check_and_update_job_status(db, job_id)
            finally:
                db.close()
        raise exc


# ---------------------------------------------------------------------------
# Document processing watchdog
# ---------------------------------------------------------------------------

_DOCUMENT_PROCESSING_TIMEOUT_MINUTES = 10


@shared_task
def document_processing_watchdog():
    """
    Watchdog for Document.processing_status, mirroring collection_watchdog's
    (collection_tasks.py) and pipeline_run_watchdog's (aggregation_tasks.py)
    staleness-sweep pattern. Runs every 15 minutes.

    Root cause this closes: execute_document_intelligence_sync above sets
    processing_status="PROCESSING" and commits before any real work happens.
    If the worker process dies anywhere after that commit (OOM kill, forced
    restart, a native-library crash in torch/spaCy, a redeploy) the document
    is stuck in PROCESSING forever -- there is no task-level time limit that
    helps here: this worker runs --pool=solo, where Celery's
    time_limit/soft_time_limit enforcement is a no-op (BasePool.on_soft_timeout/
    on_hard_timeout are unimplemented `pass`; only the prefork pool can kill a
    stuck child process, and solo has no child process to kill -- same reason
    pipeline_run_watchdog exists instead of a task decorator timeout). A
    Beat-scheduled sweep works regardless of pool type since it acts from
    outside the stuck task. Found live: 130 documents stuck up to 11+ days,
    same failure class CollectionJob and PipelineRun already hit and got a
    watchdog for -- Document never did, until now.

    Threshold: 10 minutes, derived from live-measured timing under current
    Render Postgres latency (not the historical *_processing_time_ms columns,
    which only cover the entity/topic/sentiment sub-stages and predate the
    Render migration): a cold-start run (first document on a freshly started
    worker, including one-time model/keyword-cache warm-up) measured ~68-71s
    end-to-end; steady-state (already-warm worker) measured ~26s. 10 minutes
    is ~8.5x the observed cold-start worst case, consistent with the same
    safety-margin convention pipeline_run_watchdog already uses (~7-10 min
    observed -> 60 min chosen, a similar ~6-8x margin) -- proportionally much
    shorter here since this is a single-document task, not a full client
    pipeline run.

    Deliberately excludes rows where processing_started_at IS NULL: that
    column did not exist before this fix, so every document stuck before
    this deploy has no value there. Those are a separate, already-identified
    cleanup (11-day-old stragglers) requiring its own explicit sign-off, not
    something this sweep should silently touch.
    """
    from app.models.document import Document

    log = structlog.get_logger().bind(task="document_processing_watchdog")
    db = SessionLocal()
    try:
        timeout_limit = datetime.now(timezone.utc) - timedelta(minutes=_DOCUMENT_PROCESSING_TIMEOUT_MINUTES)

        stuck_docs = db.query(Document).filter(
            Document.processing_status == "PROCESSING",
            Document.processing_started_at.isnot(None),
            Document.processing_started_at < timeout_limit,
        ).all()

        if not stuck_docs:
            log.info("watchdog_no_stuck_documents")
            return

        log.warning("watchdog_found_stuck_documents", total_stuck=len(stuck_docs))

        for doc in stuck_docs:
            doc_id_str = str(doc.id)
            log.warning("watchdog_recovering_document", document_id=doc_id_str,
                       processing_started_at=str(doc.processing_started_at))
            doc.processing_status = "PENDING"
            doc.match_failure_reason = "recovered_from_stuck_processing_by_watchdog"
            db.commit()

    except Exception as exc:
        db.rollback()
        log.error("watchdog_failed", error=str(exc))
    finally:
        db.close()

