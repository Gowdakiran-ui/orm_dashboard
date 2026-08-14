from celery import shared_task
from app.core.db import SessionLocal
from app.services.intelligence.topic_classifier import TopicClassifier
from app.services.intelligence.topic_classification_batch_processor import HardenedTopicClassifier, TopicRetryConfig
from app.services.intelligence.entity_extractor import EntityExtractor
from app.services.intelligence.sentiment_analyzer import SentimentAnalyzer
from app.services.intelligence.entity_discovery import entity_discovery_engine
import structlog
import uuid

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
            raise celery_task.retry(exc=exc, countdown=60)
        else:
            raise exc
    finally:
        entity_db.close()
    duration_matching = (time.perf_counter() - t_matching) * 1000
    print(f"[TIMING] document_id={document_id} stage=entity_matching duration_ms={duration_matching:.2f}", flush=True)

    # 2. Phase 1B: Topic Classification
    t_topic = time.perf_counter()
    try:
        hardened_topic_classifier.process_batch(
            document_ids=[document_id],
            client_id=client_id,
            batch_id=uuid.uuid4().hex[:12]
        )
    except Exception as topic_exc:
        logger.error("topic_classification_failed_stage_isolated", document_id=document_id, error=str(topic_exc))
    duration_topic = (time.perf_counter() - t_topic) * 1000
    print(f"[TIMING] document_id={document_id} stage=topic_classification duration_ms={duration_topic:.2f}", flush=True)

    # 3. Phase 1C: Sentiment Analysis
    t_sentiment = time.perf_counter()
    try:
        from app.services.intelligence.sentiment_batch_processor import HardenedSentimentProcessor
        hardened_sentiment = HardenedSentimentProcessor(analyzer_instance=sentiment_analyzer)
        hardened_sentiment.process_batch(
            document_ids=[document_id],
            client_id=client_id,
            batch_id=uuid.uuid4().hex[:12]
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



