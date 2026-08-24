import uuid
import time
import os
import re
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.core.db import SessionLocal
from app.models.document import Document
from app.models.entity import Entity, EntityMention
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.system import ModelRun
from app.models.source import Source, SourceCategory
from app.services.intelligence.sentiment_analyzer import SentimentAnalyzer

# ─────────────────────────────────────────────────────────────
# CORRELATED LOGGING UTILITY — Matches Topic Classification & Entity Matching
# ─────────────────────────────────────────────────────────────

class CorrelatedLogger:
    def __init__(self, name: str, context: Optional[Dict[str, Any]] = None):
        self.name = name
        self.context = context or {}
        import logging
        self._logger = logging.getLogger(name)

    def bind(self, **kwargs) -> 'CorrelatedLogger':
        return CorrelatedLogger(self.name, {**self.context, **kwargs})

    def _format(self, event: str, **kwargs) -> str:
        all_ctx = {**self.context, **kwargs}
        all_ctx["event"] = event
        all_ctx["ts"] = datetime.now(timezone.utc).isoformat()
        
        parts = []
        # Print core correlation IDs first for high readability
        for k in ["run_id", "batch_id", "client_id", "worker_id", "processing_stage", "document_id", "event"]:
            if k in all_ctx:
                parts.append(f'{k}="{all_ctx.pop(k)}"')
        for k, v in sorted(all_ctx.items()):
            if isinstance(v, float):
                parts.append(f'{k}={round(v, 4)}')
            elif isinstance(v, int):
                parts.append(f'{k}={v}')
            elif isinstance(v, bool):
                parts.append(f'{k}={"true" if v else "false"}')
            else:
                parts.append(f'{k}="{str(v)}"')
        return " | ".join(parts)

    def debug(self, event: str, **kwargs):
        self._logger.debug(self._format(event, **kwargs))

    def info(self, event: str, **kwargs):
        self._logger.info(self._format(event, **kwargs))

    def warning(self, event: str, **kwargs):
        self._logger.warning(self._format(event, **kwargs))

    def error(self, event: str, **kwargs):
        self._logger.error(self._format(event, **kwargs))


import logging
logger = CorrelatedLogger("sentiment.batch_processor")

# ─────────────────────────────────────────────────────────────
# SENTIMENT PROCESSING STATES — Phase R3
# ─────────────────────────────────────────────────────────────

class SentimentProcessingState:
    PENDING    = "SENTIMENT_PENDING"
    PROCESSING = "SENTIMENT_PROCESSING"
    COMPLETE   = "SENTIMENT_COMPLETE"
    FAILED     = "SENTIMENT_FAILED"
    RETRYING   = "SENTIMENT_RETRYING"
    SKIPPED    = "SENTIMENT_SKIPPED"

    TRANSITIONS = {
        PENDING:    {PROCESSING, SKIPPED, RETRYING, FAILED},
        PROCESSING: {COMPLETE, FAILED, SKIPPED, RETRYING},
        RETRYING:   {PROCESSING, RETRYING, FAILED},
        FAILED:     {PROCESSING},   # Allow resuming/retrying from FAILED
        COMPLETE:   {PROCESSING},   # Allow reprocessing
        SKIPPED:    {PROCESSING}    # Allow reprocessing skipped
    }

    @classmethod
    def is_valid_transition(cls, from_state: str, to_state: str) -> bool:
        allowed = cls.TRANSITIONS.get(from_state, set())
        return to_state in allowed

# ─────────────────────────────────────────────────────────────
# RETRY CONFIGURATION — Phase R2
#
# See RetryConfig's comment in entity_matching_batch_processor.py for the
# full 4-pattern retry/backoff inventory (FINDINGS.md #18). This is pattern
# 3 of 4 -- an in-process retry state machine, mirrored by RetryConfig and
# TopicRetryConfig.
# ─────────────────────────────────────────────────────────────

@dataclass
class SentimentRetryConfig:
    max_retries: int = 3
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    permanent_failure_patterns: List[str] = None

    def __post_init__(self):
        if self.permanent_failure_patterns is None:
            self.permanent_failure_patterns = [
                "UnicodeDecodeError",
                "document_not_found",
                "ValueError",
                "AttributeError",
                "RuntimeError" # E.g. mock production guard violation is permanent
            ]

    def backoff_seconds(self, retry_count: int) -> float:
        delay = self.base_backoff_seconds * (2 ** retry_count)
        return min(delay, self.max_backoff_seconds)

    def is_permanent_failure(self, exception_type: str, failure_reason: str) -> bool:
        for pattern in self.permanent_failure_patterns:
            if pattern in exception_type or pattern in failure_reason:
                return True
        return False

# ─────────────────────────────────────────────────────────────
# STATE MACHINE UTILITY
# ─────────────────────────────────────────────────────────────

class SentimentDocumentStateMachine:
    """
    Manages atomic document state transitions in PostgreSQL for Sentiment Analysis.
    Runs in a dedicated transaction to ensure isolation.
    """
    @staticmethod
    def transition(
        db: Session,
        document_id: str,
        to_state: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
        retry_count: Optional[int] = None,
        processing_time_ms: Optional[float] = None,
    ) -> bool:
        doc = db.query(Document).filter(Document.id == document_id).with_for_update().first()
        if not doc:
            return False

        current = doc.sentiment_processing_status or SentimentProcessingState.PENDING
        if not SentimentProcessingState.is_valid_transition(current, to_state):
            raise ValueError(
                f"Invalid state transition: {current} -> {to_state} for document {document_id}"
            )

        doc.sentiment_processing_status = to_state
        if run_id is not None:
            doc.sentiment_run_id = run_id
        if batch_id is not None:
            doc.sentiment_batch_id = batch_id
        if failure_reason is not None:
            doc.sentiment_failure_reason = str(failure_reason)[:4000]
        if retry_count is not None:
            doc.sentiment_retry_count = retry_count
        if processing_time_ms is not None:
            doc.sentiment_processing_time_ms = processing_time_ms
        if to_state == SentimentProcessingState.FAILED:
            doc.sentiment_failed_at = datetime.now(timezone.utc)

        return True

    @staticmethod
    def transition_and_commit(
        document_id: str,
        to_state: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
        retry_count: Optional[int] = None,
        processing_time_ms: Optional[float] = None,
    ) -> bool:
        db = SessionLocal()
        try:
            ok = SentimentDocumentStateMachine.transition(
                db, document_id, to_state,
                run_id=run_id, batch_id=batch_id,
                failure_reason=failure_reason,
                retry_count=retry_count,
                processing_time_ms=processing_time_ms,
            )
            if ok:
                db.commit()
            return ok
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

# ─────────────────────────────────────────────────────────────
# HARDENED SENTIMENT BATCH PROCESSOR
# ─────────────────────────────────────────────────────────────

@dataclass
class SentimentDocumentResult:
    document_id: str
    state: str
    processing_time_ms: float = 0.0
    retry_count: int = 0
    failure_reason: Optional[str] = None
    exception_type: Optional[str] = None
    stack_trace: Optional[str] = None

@dataclass
class SentimentBatchResult:
    run_id: str
    batch_id: str
    client_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_documents: int = 0
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    retried: int = 0
    db_rollbacks: int = 0
    document_results: List[SentimentDocumentResult] = None

    def __post_init__(self):
        if self.document_results is None:
            self.document_results = []

    def summary(self) -> Dict[str, Any]:
        elapsed = (self.completed_at - self.started_at).total_seconds() if self.completed_at else 0
        return {
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "client_id": self.client_id,
            "elapsed_seconds": round(elapsed, 2),
            "total": self.total_documents,
            "processed": self.processed,
            "failed": self.failed,
            "skipped": self.skipped,
            "retried": self.retried,
            "db_rollbacks": self.db_rollbacks
        }

class HardenedSentimentProcessor:
    """
    Production-grade, highly reliable Sentiment Analysis engine.
    Ensures:
      - Per-document isolated transactions (R4)
      - Concurrency & duplicate write protection via safe UPSERT ON CONFLICT DO UPDATE (R5)
      - Detailed structured logging with full correlation context (R7)
      - Transient/permanent retry isolation with exponential backoff (R2)
      - Deterministic state machine transitions (R3)
    """
    def __init__(
        self,
        analyzer_instance: SentimentAnalyzer,
        retry_config: Optional[SentimentRetryConfig] = None,
        worker_id: Optional[str] = None
    ):
        self.analyzer = analyzer_instance
        self.retry_config = retry_config or SentimentRetryConfig()
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"

    def _process_single_document_in_transaction(
        self,
        document_id: str,
        run_id: str,
        batch_id: str,
        client_id: str,
        doc_logger: CorrelatedLogger
    ) -> SentimentDocumentResult:
        start_time = time.perf_counter()
        db = SessionLocal()

        try:
            # Pre-flight state check
            doc_check = db.query(Document).filter(Document.id == document_id).first()
            if doc_check and doc_check.sentiment_processing_status == SentimentProcessingState.COMPLETE:
                status = doc_check.sentiment_processing_status
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                doc_logger.info("document_skipped_already_processed",
                                document_id=document_id,
                                current_state=status)
                return SentimentDocumentResult(
                    document_id=document_id,
                    state=SentimentProcessingState.SKIPPED,
                    processing_time_ms=elapsed
                )

            # Keep track of retry count in local variable before closing/committing
            local_retry_count = doc_check.sentiment_retry_count if doc_check else 0

            # STEP 1: Set state to PROCESSING (atomic, locks row)
            transition_ok = SentimentDocumentStateMachine.transition(
                db, document_id, SentimentProcessingState.PROCESSING,
                run_id=run_id, batch_id=batch_id
            )
            if not transition_ok:
                doc_logger.warning("document_not_found_skipping", document_id=document_id)
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                return SentimentDocumentResult(
                    document_id=document_id,
                    state=SentimentProcessingState.SKIPPED,
                    processing_time_ms=elapsed,
                    failure_reason="document_not_found"
                )

            # Commit the PROCESSING state immediately to let other workers know
            db.commit()

            # STEP 2: Fetch document content
            doc = db.query(Document).filter(Document.id == document_id).first()
            content = doc.normalized_content if doc else None

            # Handle missing text / empty text / corrupt HTML (R9)
            if not doc or content is None or not str(content).strip():
                # Transition to SKIPPED rather than hard crash, keeping pipeline running
                SentimentDocumentStateMachine.transition(
                    db, document_id, SentimentProcessingState.SKIPPED,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason="empty_or_missing_content"
                )
                db.commit()
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                doc_logger.info("document_skipped_empty_content", document_id=document_id)
                return SentimentDocumentResult(
                    document_id=document_id,
                    state=SentimentProcessingState.SKIPPED,
                    processing_time_ms=elapsed,
                    failure_reason="empty_content"
                )

            doc_logger.info("sentiment_analysis_started", content_length=len(content))

            # Import accuracy hardening utilities (Phase 3.2)
            from app.services.intelligence.sentiment_accuracy_enhancer import (
                preprocess_text,
                apply_orm_rules,
                get_dynamic_source_reliability
            )

            # Query matched entity keywords for smart content extraction.
            # Reads from EntityMention (accuracy-gated, per evaluate_match_accuracy)
            # rather than the ungated DocumentMatch table -- see FINDINGS.md.
            matches = db.query(EntityMention).filter(EntityMention.document_id == document_id).all()
            matched_keywords = set()
            for m in matches:
                ent = db.query(Entity).filter(Entity.id == m.entity_id).first()
                if ent:
                    matched_keywords.add(ent.name)

            # 1. Advanced Preprocessing (A2)
            preprocessed_text = preprocess_text(
                content,
                title=doc.title or "",
                summary="",
                matched_keywords=matched_keywords
            )
            if not preprocessed_text.strip():
                preprocessed_text = content

            # 2. Run FinBERT on preprocessed text
            raw_result = self.analyzer.analyze_text(preprocessed_text)
            raw_label = raw_result.get("label", "neutral").lower()
            raw_score = raw_result.get("score", 1.0)

            # 3. Apply ORM Context Rules & Calibration (A3 + A4)
            orm_res = apply_orm_rules(preprocessed_text, raw_label, raw_score)
            calibrated_label = orm_res["label"]
            calibrated_score = orm_res["score"]

            score_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
            sentiment_score = score_map.get(calibrated_label, 0.0)

            # 4. Dynamic Source Reliability (A6)
            source_reliability = get_dynamic_source_reliability(db, doc.source_id, doc.url)
            weighted_score = sentiment_score * source_reliability

            # 5. Generate Explainability Metadata (A5)
            # Find best supporting sentence based on keyword matching
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', preprocessed_text) if s.strip()]
            supporting_sentence = sentences[0] if sentences else ""
            supporting_keywords = orm_res["trigger_words"]
            for sent in sentences:
                if any(w.lower() in sent.lower() for w in supporting_keywords):
                    supporting_sentence = sent
                    break

            rejected_labels = [
                {"label": "Neutral", "confidence": round(raw_score, 4) if raw_label == "neutral" else 0.0},
                {"label": "Positive", "confidence": round(raw_score, 4) if raw_label == "positive" else 0.0},
                {"label": "Negative", "confidence": round(raw_score, 4) if raw_label == "negative" else 0.0}
            ]

            doc_explainability = {
                "sentiment": calibrated_label.capitalize(),
                "confidence": round(calibrated_score, 4),
                "supporting_sentence": supporting_sentence,
                "supporting_keywords": supporting_keywords,
                "detected_evidence": orm_res["applied_rule"],
                "rejected_labels": rejected_labels,
                "decision_reason": f"Calibrated via ORM rule: {orm_res['applied_rule']} (Raw: {raw_label} {round(raw_score, 4)}).",
                "model_version": f"{self.analyzer.model_name} (v{self.analyzer.model_version}) + ORM rules v1.0"
            }

            # Safe Upsert for DocumentSentiment (R5 + A5)
            ds_id = uuid.uuid4()
            stmt_ds = insert(DocumentSentiment).values(
                id=ds_id,
                document_id=document_id,
                sentiment_label=calibrated_label.capitalize(),
                sentiment_score=sentiment_score,
                confidence_score=calibrated_score,
                source_reliability=source_reliability,
                weighted_sentiment_score=weighted_score,
                explainability_metadata=doc_explainability,
                created_at=datetime.now(timezone.utc)
            ).on_conflict_do_update(
                constraint="uq_document_sentiments_document_id",
                set_={
                    "sentiment_label": calibrated_label.capitalize(),
                    "sentiment_score": sentiment_score,
                    "confidence_score": calibrated_score,
                    "source_reliability": source_reliability,
                    "weighted_sentiment_score": weighted_score,
                    "explainability_metadata": doc_explainability,
                    "created_at": datetime.now(timezone.utc)
                }
            )
            db.execute(stmt_ds)

            # 6. Localized Entity-Level Sentiment (A7)
            for m in matches:
                ent = db.query(Entity).filter(Entity.id == m.entity_id).first()
                if not ent:
                    continue
                
                # Get surrounding context window for entity (200 characters around it)
                context = self.analyzer.get_entity_context(content, ent.name, window=200)
                # Apply advanced preprocessing to entity context too
                ent_preprocessed = preprocess_text(context, title="", summary="", matched_keywords={ent.name})
                if not ent_preprocessed.strip():
                    ent_preprocessed = context

                ent_raw = self.analyzer.analyze_text(ent_preprocessed)
                ent_raw_label = ent_raw.get("label", "neutral").lower()
                ent_raw_score = ent_raw.get("score", 1.0)

                # Calibrate locally
                ent_orm = apply_orm_rules(ent_preprocessed, ent_raw_label, ent_raw_score)
                ent_calibrated_label = ent_orm["label"]
                ent_calibrated_score = ent_orm["score"]
                ent_sentiment_score = score_map.get(ent_calibrated_label, 0.0)

                ent_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', ent_preprocessed) if s.strip()]
                ent_supporting = ent_sentences[0] if ent_sentences else ""
                for esent in ent_sentences:
                    if ent.name.lower() in esent.lower():
                        ent_supporting = esent
                        break

                ent_explainability = {
                    "sentiment": ent_calibrated_label.capitalize(),
                    "confidence": round(ent_calibrated_score, 4),
                    "supporting_sentence": ent_supporting,
                    "supporting_keywords": ent_orm["trigger_words"],
                    "detected_evidence": ent_orm["applied_rule"],
                    "rejected_labels": [
                        {"label": "Neutral", "confidence": round(ent_raw_score, 4) if ent_raw_label == "neutral" else 0.0},
                        {"label": "Positive", "confidence": round(ent_raw_score, 4) if ent_raw_label == "positive" else 0.0},
                        {"label": "Negative", "confidence": round(ent_raw_score, 4) if ent_raw_label == "negative" else 0.0}
                    ],
                    "decision_reason": f"Localized entity sentiment for {ent.name} calibrated via: {ent_orm['applied_rule']}.",
                    "model_version": f"{self.analyzer.model_name} (v{self.analyzer.model_version}) + ORM rules v1.0"
                }

                # Safe Upsert for EntitySentiment (R5)
                es_id = uuid.uuid4()
                stmt_es = insert(EntitySentiment).values(
                    id=es_id,
                    document_id=document_id,
                    entity_id=ent.id,
                    sentiment_label=ent_calibrated_label.capitalize(),
                    sentiment_score=ent_sentiment_score,
                    confidence_score=ent_calibrated_score,
                    explainability_metadata=ent_explainability,
                    created_at=datetime.now(timezone.utc)
                ).on_conflict_do_update(
                    constraint="uq_entity_sentiments_doc_entity",
                    set_={
                        "sentiment_label": ent_calibrated_label.capitalize(),
                        "sentiment_score": ent_sentiment_score,
                        "confidence_score": ent_calibrated_score,
                        "explainability_metadata": ent_explainability,
                        "created_at": datetime.now(timezone.utc)
                    }
                )
                db.execute(stmt_es)

            # STEP 5: Log the Model Run (Safe unique/overwrite or append)
            # To prevent model run duplicates or bloating, we can write it
            run_log = ModelRun(
                document_id=document_id,
                model_name=self.analyzer.model_name,
                model_version=self.analyzer.model_version
            )
            db.add(run_log)

            # STEP 6: Mark document processing as COMPLETE (R3)
            elapsed = (time.perf_counter() - start_time) * 1000
            SentimentDocumentStateMachine.transition(
                db, document_id, SentimentProcessingState.COMPLETE,
                run_id=run_id, batch_id=batch_id,
                processing_time_ms=elapsed
            )

            # Commit atomic transaction (R4)
            db.commit()
            db.close()

            # Structured logging on success (R7)
            doc_logger.info(
                "sentiment_analysis_success",
                processing_stage="SENTIMENT_ANALYSIS",
                model_name=self.analyzer.model_name,
                model_version=self.analyzer.model_version,
                latency=round(elapsed, 2),
                confidence=round(calibrated_score, 4),
                retry_count=local_retry_count,
                processing_state=SentimentProcessingState.COMPLETE
            )

            return SentimentDocumentResult(
                document_id=document_id,
                state=SentimentProcessingState.COMPLETE,
                processing_time_ms=elapsed,
                retry_count=local_retry_count
            )

        except Exception as e:
            # Atomic rollback on failure of this single document (R4)
            db.rollback()
            db.close()
            
            elapsed = (time.perf_counter() - start_time) * 1000
            err_msg = str(e)
            exc_type = type(e).__name__
            stack = traceback.format_exc()

            # Structured logging on failure (R7)
            doc_logger.error(
                "sentiment_analysis_document_failed",
                exception=exc_type,
                traceback=stack,
                retry=True,
                classification="transient" if not self.retry_config.is_permanent_failure(exc_type, err_msg) else "permanent"
            )

            return SentimentDocumentResult(
                document_id=document_id,
                state=SentimentProcessingState.FAILED,
                processing_time_ms=elapsed,
                failure_reason=err_msg,
                exception_type=exc_type,
                stack_trace=stack
            )

    def _process_with_retry(
        self,
        document_id: str,
        run_id: str,
        batch_id: str,
        client_id: str,
        current_retry_count: int,
        doc_logger: CorrelatedLogger
    ) -> SentimentDocumentResult:
        result = self._process_single_document_in_transaction(
            document_id, run_id, batch_id, client_id, doc_logger
        )

        if result.state == SentimentProcessingState.FAILED:
            is_permanent = self.retry_config.is_permanent_failure(
                result.exception_type or "",
                result.failure_reason or ""
            )
            can_retry = (
                not is_permanent
                and current_retry_count < self.retry_config.max_retries
            )

            if can_retry:
                new_retry_count = current_retry_count + 1
                backoff = self.retry_config.backoff_seconds(current_retry_count)

                doc_logger.info("document_retry_scheduled",
                                retry_attempt=new_retry_count,
                                max_retries=self.retry_config.max_retries,
                                backoff_seconds=round(backoff, 2),
                                failure_reason=result.failure_reason)

                # Persist RETRYING state in a separate session
                SentimentDocumentStateMachine.transition_and_commit(
                    document_id, SentimentProcessingState.RETRYING,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason=result.failure_reason,
                    retry_count=new_retry_count
                )

                if backoff > 0:
                    time.sleep(min(backoff, 5.0))  # Cap sleep at 5s in worker loop

                retry_logger = doc_logger.bind(retry_count=new_retry_count)
                retry_logger.info("document_retry_attempt_started", retry_attempt=new_retry_count)

                # Run retry inside transaction
                retried_result = self._process_single_document_in_transaction(
                    document_id, run_id, batch_id, client_id, retry_logger
                )
                retried_result.retry_count = new_retry_count
                return retried_result

            else:
                doc_logger.error("document_permanently_failed",
                                 retry_count=current_retry_count,
                                 is_permanent=is_permanent,
                                 failure_reason=result.failure_reason)

                # Persist terminal FAILED state in a separate session
                SentimentDocumentStateMachine.transition_and_commit(
                    document_id, SentimentProcessingState.FAILED,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason=result.failure_reason,
                    retry_count=current_retry_count
                )

        return result

    def process_batch(
        self,
        document_ids: List[str],
        client_id: str,
        batch_id: Optional[str] = None,
        batch_size: int = 16
    ) -> SentimentBatchResult:
        started_at = datetime.now(timezone.utc)
        run_id = str(uuid.uuid4())
        bid = batch_id or uuid.uuid4().hex[:12]

        batch_logger = logger.bind(
            run_id=run_id,
            batch_id=bid,
            client_id=client_id,
            worker_id=self.worker_id,
            processing_stage="SENTIMENT_BATCH"
        )

        batch_logger.info("sentiment_batch_started", total_documents=len(document_ids), batch_size=batch_size)
        result = SentimentBatchResult(
            run_id=run_id,
            batch_id=bid,
            client_id=client_id,
            started_at=started_at,
            total_documents=len(document_ids)
        )

        # STAGE 1: Lock Rows, Preprocess, and Prepare Texts in isolated steps
        prepared_docs = []
        from app.services.intelligence.sentiment_accuracy_enhancer import (
            preprocess_text,
            apply_orm_rules,
            get_dynamic_source_reliability
        )

        db = SessionLocal()
        try:
            for doc_id in document_ids:
                doc_logger = batch_logger.bind(document_id=doc_id)
                try:
                    # Pre-flight check
                    doc_check = db.query(Document).filter(Document.id == doc_id).first()
                    if doc_check and doc_check.sentiment_processing_status == SentimentProcessingState.COMPLETE:
                        result.skipped += 1
                        continue

                    # Transition state to PROCESSING
                    transition_ok = SentimentDocumentStateMachine.transition(
                        db, doc_id, SentimentProcessingState.PROCESSING,
                        run_id=run_id, batch_id=bid
                    )
                    if not transition_ok:
                        result.skipped += 1
                        continue

                    # Fetch text and matches
                    doc = db.query(Document).filter(Document.id == doc_id).first()
                    content = doc.normalized_content if doc else None
                    title = doc.title or ""
                    source_id = doc.source_id if doc else None
                    url = doc.url if doc else None
                    local_retry = doc.sentiment_retry_count if doc else 0

                    if not doc or content is None or not str(content).strip():
                        doc.sentiment_processing_status = SentimentProcessingState.SKIPPED
                        doc.sentiment_failure_reason = "empty_or_missing_content"
                        db.commit()
                        result.skipped += 1
                        continue

                    # Bulk fetch matches and their entities to avoid N+1 queries.
                    # Reads from EntityMention (accuracy-gated) rather than the
                    # ungated DocumentMatch table -- see FINDINGS.md.
                    matches = db.query(EntityMention).filter(EntityMention.document_id == doc_id).all()
                    matched_keywords = set()
                    entity_details = []
                    if matches:
                        entity_ids = [m.entity_id for m in matches]
                        entities = db.query(Entity).filter(Entity.id.in_(entity_ids)).all()
                        entity_map = {e.id: e.name for e in entities}
                        for m in matches:
                            ent_name = entity_map.get(m.entity_id)
                            if ent_name:
                                matched_keywords.add(ent_name)
                                entity_details.append({"id": m.entity_id, "name": ent_name})

                    db.commit()

                    # Preprocess text
                    preprocessed = preprocess_text(content, title=title, summary="", matched_keywords=matched_keywords)
                    if not preprocessed.strip():
                        preprocessed = content

                    prepared_docs.append({
                        "id": doc_id,
                        "preprocessed_text": preprocessed,
                        "raw_content": content,
                        "source_id": source_id,
                        "url": url,
                        "local_retry_count": local_retry,
                        "entities": entity_details,
                        "logger": doc_logger
                    })

                except Exception as prep_exc:
                    db.rollback()
                    SentimentDocumentStateMachine.transition_and_commit(
                        doc_id, SentimentProcessingState.FAILED,
                        run_id=run_id, batch_id=bid,
                        failure_reason=f"Preparation failed: {str(prep_exc)}"
                    )
                    result.failed += 1
        finally:
            db.close()

        if not prepared_docs:
            result.completed_at = datetime.now(timezone.utc)
            batch_logger.info("sentiment_batch_completed", **result.summary())
            return result

        # STAGE 2: Batch Inference (Fast parallel model forward passes)
        texts_to_analyze = [d["preprocessed_text"] for d in prepared_docs]
        
        # Collect all entity contexts across all documents to batch them too
        entity_tasks = []
        for p in prepared_docs:
            for ent_info in p["entities"]:
                context = self.analyzer.get_entity_context(p["raw_content"], ent_info["name"], window=200)
                entity_tasks.append({
                    "doc_id": p["id"],
                    "ent_id": ent_info["id"],
                    "ent_name": ent_info["name"],
                    "preprocessed_text": context
                })

        try:
            # Run document level batch inference
            batch_raw_results = self.analyzer.analyze_batch(texts_to_analyze, batch_size=batch_size)
            
            # Run entity level batch inference in a single call (no sequential loops)
            entity_raw_results = []
            if entity_tasks:
                ent_texts = [et["preprocessed_text"] for et in entity_tasks]
                entity_raw_results = self.analyzer.analyze_batch(ent_texts, batch_size=batch_size)
        except Exception as inf_exc:
            for p in prepared_docs:
                SentimentDocumentStateMachine.transition_and_commit(
                    p["id"], SentimentProcessingState.FAILED,
                    run_id=run_id, batch_id=bid,
                    failure_reason=f"Batch inference failed: {str(inf_exc)}"
                )
                result.failed += 1
            result.completed_at = datetime.now(timezone.utc)
            batch_logger.info("sentiment_batch_completed", **result.summary())
            return result

        # Map entity results back to their tasks
        entity_results_map = {}
        for task, res in zip(entity_tasks, entity_raw_results):
            doc_id = task["doc_id"]
            if doc_id not in entity_results_map:
                entity_results_map[doc_id] = []
            entity_results_map[doc_id].append({
                "ent_id": task["ent_id"],
                "ent_name": task["ent_name"],
                "preprocessed_text": task["preprocessed_text"],
                "raw_result": res
            })

        # STAGE 3: DB Writes & Localized Entity Sentiment (Isolated per document)
        db = SessionLocal()
        source_cache = {}
        category_cache = {}

        def get_cached_reliability(source_id, url):
            if not source_id:
                return 1.0
            if source_id not in source_cache:
                source = db.query(Source).filter(Source.id == source_id).first()
                source_cache[source_id] = source
            else:
                source = source_cache[source_id]
                
            if not source:
                return 1.0
                
            category_id = source.category_id
            if category_id:
                if category_id not in category_cache:
                    category = db.query(SourceCategory).filter(SourceCategory.id == category_id).first()
                    category_cache[category_id] = category
                else:
                    category = category_cache[category_id]
                reliability = float(category.base_reliability_score or 1.0) if category else 1.0
            else:
                reliability = 1.0
                
            st_lower = str(source.source_type).lower()
            if "reddit" in st_lower or "forum" in st_lower or "social" in st_lower:
                reliability = min(reliability, 0.60)
            elif "rss" in st_lower:
                url_lower = str(url or source.url).lower()
                if any(domain in url_lower for domain in ["reuters.com", "bloomberg.com", "wsj.com", "nytimes.com", "ft.com"]):
                    reliability = 1.00
                else:
                    reliability = min(reliability, 0.80)
            return reliability

        try:
            for p, raw_res in zip(prepared_docs, batch_raw_results):
                doc_id = p["id"]
                preprocessed_text = p["preprocessed_text"]
                content = p["raw_content"]
                source_id = p["source_id"]
                url = p["url"]
                local_retry_count = p["local_retry_count"]
                doc_logger = p["logger"]

                t_start = time.perf_counter()
                try:
                    # Lock row
                    doc = db.query(Document).filter(Document.id == doc_id).with_for_update().first()

                    raw_label = raw_res.get("label", "neutral").lower()
                    raw_score = raw_res.get("score", 1.0)

                    # ORM Rules & Calibration
                    orm_res = apply_orm_rules(preprocessed_text, raw_label, raw_score)
                    calibrated_label = orm_res["label"]
                    calibrated_score = orm_res["score"]

                    score_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
                    sentiment_score = score_map.get(calibrated_label, 0.0)

                    # Dynamic Source Reliability
                    source_reliability = get_cached_reliability(source_id, url)
                    weighted_score = sentiment_score * source_reliability

                    # Explainability Metadata
                    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', preprocessed_text) if s.strip()]
                    supporting_sentence = sentences[0] if sentences else ""
                    supporting_keywords = orm_res["trigger_words"]
                    for sent in sentences:
                        if any(w.lower() in sent.lower() for w in supporting_keywords):
                            supporting_sentence = sent
                            break

                    rejected_labels = [
                        {"label": "Neutral", "confidence": round(raw_score, 4) if raw_label == "neutral" else 0.0},
                        {"label": "Positive", "confidence": round(raw_score, 4) if raw_label == "positive" else 0.0},
                        {"label": "Negative", "confidence": round(raw_score, 4) if raw_label == "negative" else 0.0}
                    ]

                    doc_explainability = {
                        "sentiment": calibrated_label.capitalize(),
                        "confidence": round(calibrated_score, 4),
                        "supporting_sentence": supporting_sentence,
                        "supporting_keywords": supporting_keywords,
                        "detected_evidence": orm_res["applied_rule"],
                        "rejected_labels": rejected_labels,
                        "decision_reason": f"Calibrated via ORM rule: {orm_res['applied_rule']} (Raw: {raw_label} {round(raw_score, 4)}).",
                        "model_version": f"{self.analyzer.model_name} (v{self.analyzer.model_version}) + ORM rules v1.0"
                    }

                    # Upsert DocumentSentiment
                    ds_id = uuid.uuid4()
                    stmt_ds = insert(DocumentSentiment).values(
                        id=ds_id,
                        document_id=doc_id,
                        sentiment_label=calibrated_label.capitalize(),
                        sentiment_score=sentiment_score,
                        confidence_score=calibrated_score,
                        source_reliability=source_reliability,
                        weighted_sentiment_score=weighted_score,
                        explainability_metadata=doc_explainability,
                        created_at=datetime.now(timezone.utc)
                    ).on_conflict_do_update(
                        constraint="uq_document_sentiments_document_id",
                        set_={
                            "sentiment_label": calibrated_label.capitalize(),
                            "sentiment_score": sentiment_score,
                            "confidence_score": calibrated_score,
                            "source_reliability": source_reliability,
                            "weighted_sentiment_score": weighted_score,
                            "explainability_metadata": doc_explainability,
                            "created_at": datetime.now(timezone.utc)
                        }
                    )
                    db.execute(stmt_ds)

                    # Localized Entity-Level Sentiment (Batch-calibrated)
                    for ent_task in entity_results_map.get(doc_id, []):
                        ent_id = ent_task["ent_id"]
                        ent_name = ent_task["ent_name"]
                        ent_preprocessed = ent_task["preprocessed_text"]
                        ent_raw = ent_task["raw_result"]

                        ent_raw_label = ent_raw.get("label", "neutral").lower()
                        ent_raw_score = ent_raw.get("score", 1.0)

                        ent_orm = apply_orm_rules(ent_preprocessed, ent_raw_label, ent_raw_score)
                        ent_calibrated_label = ent_orm["label"]
                        ent_calibrated_score = ent_orm["score"]
                        ent_sentiment_score = score_map.get(ent_calibrated_label, 0.0)

                        ent_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', ent_preprocessed) if s.strip()]
                        ent_supporting = ent_sentences[0] if ent_sentences else ""
                        for esent in ent_sentences:
                            if ent_name.lower() in esent.lower():
                                ent_supporting = esent
                                break

                        ent_explainability = {
                            "sentiment": ent_calibrated_label.capitalize(),
                            "confidence": round(ent_calibrated_score, 4),
                            "supporting_sentence": ent_supporting,
                            "supporting_keywords": ent_orm["trigger_words"],
                            "detected_evidence": ent_orm["applied_rule"],
                            "rejected_labels": [
                                {"label": "Neutral", "confidence": round(ent_raw_score, 4) if ent_raw_label == "neutral" else 0.0},
                                {"label": "Positive", "confidence": round(ent_raw_score, 4) if ent_raw_label == "positive" else 0.0},
                                {"label": "Negative", "confidence": round(ent_raw_score, 4) if ent_raw_label == "negative" else 0.0}
                            ],
                            "decision_reason": f"Localized entity sentiment for {ent_name} calibrated via: {ent_orm['applied_rule']}.",
                            "model_version": f"{self.analyzer.model_name} (v{self.analyzer.model_version}) + ORM rules v1.0"
                        }

                        es_id = uuid.uuid4()
                        stmt_es = insert(EntitySentiment).values(
                            id=es_id,
                            document_id=doc_id,
                            entity_id=ent_id,
                            sentiment_label=ent_calibrated_label.capitalize(),
                            sentiment_score=ent_sentiment_score,
                            confidence_score=ent_calibrated_score,
                            explainability_metadata=ent_explainability,
                            created_at=datetime.now(timezone.utc)
                        ).on_conflict_do_update(
                            constraint="uq_entity_sentiments_doc_entity",
                            set_={
                                "sentiment_label": ent_calibrated_label.capitalize(),
                                "sentiment_score": ent_sentiment_score,
                                "confidence_score": ent_calibrated_score,
                                "explainability_metadata": ent_explainability,
                                "created_at": datetime.now(timezone.utc)
                            }
                        )
                        db.execute(stmt_es)

                    # Log Model Run
                    run_log = ModelRun(
                        document_id=doc_id,
                        model_name=self.analyzer.model_name,
                        model_version=self.analyzer.model_version
                    )
                    db.add(run_log)

                    # Transition state to COMPLETE
                    elapsed = (time.perf_counter() - t_start) * 1000
                    doc.sentiment_processing_status = SentimentProcessingState.COMPLETE
                    doc.sentiment_processing_time_ms = elapsed
                    doc.sentiment_run_id = run_id
                    doc.sentiment_batch_id = bid

                    db.commit()

                    doc_logger.info(
                        "sentiment_analysis_success",
                        processing_stage="SENTIMENT_ANALYSIS",
                        model_name=self.analyzer.model_name,
                        model_version=self.analyzer.model_version,
                        latency=round(elapsed, 2),
                        confidence=round(calibrated_score, 4),
                        retry_count=local_retry_count,
                        processing_state=SentimentProcessingState.COMPLETE
                    )
                    result.processed += 1

                except Exception as e:
                    db.rollback()
                    
                    elapsed = (time.perf_counter() - t_start) * 1000
                    err_msg = str(e)
                    exc_type = type(e).__name__
                    stack = traceback.format_exc()

                    doc_logger.error(
                        "sentiment_analysis_document_failed",
                        exception=exc_type,
                        traceback=stack,
                        retry=False,
                        classification="permanent"
                    )

                    # Mark as FAILED
                    SentimentDocumentStateMachine.transition_and_commit(
                        doc_id, SentimentProcessingState.FAILED,
                        run_id=run_id, batch_id=bid,
                        failure_reason=err_msg,
                        retry_count=local_retry_count
                    )
                    result.failed += 1
        finally:
            db.close()

        result.completed_at = datetime.now(timezone.utc)
        batch_logger.info("sentiment_batch_completed", **result.summary())
        return result
