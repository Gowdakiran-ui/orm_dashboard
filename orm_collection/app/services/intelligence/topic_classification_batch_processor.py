import uuid
import time
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.core.db import SessionLocal
from app.models.document import Document
from app.models.entity import Entity, EntityMention
from app.models.topic import Topic, DocumentTopic
from app.models.system import ModelRun
from app.utils.text_processing import canonicalize_url
from app.utils.topic_preprocessing import preprocess_document_text
from app.services.intelligence.negative_suppression import apply_negative_suppression
import re

# ─────────────────────────────────────────────────────────────
# EXPLAINABILITY HELPERS & TAXONOMY KEYWORDS — Phase A5
# ─────────────────────────────────────────────────────────────

TOPIC_KEYWORDS = {
    "Financial Results": ["earnings", "financials", "target of rs", "stock to buy"],
    "Executive Leadership": ["entrepreneur", "lead whatsapp", "tapped by meta"],
    "Product Launch": ["launches cheaper", "smart glasses", "secures over", "electric cv orders"],
    "Legal Risk": ["misleading", "safety data to"],
    "Regulatory Risk": ["safety data to", "halts worker tracking", "due to privacy"],
    "Environmental": ["sustainability", "esg", "carbon"],
    "Cybersecurity": ["cybersecurity", "breach", "hack"],
    "Labor Relations": ["halts worker tracking", "worker tracking for"],
    "Mergers & Acquisitions": ["potential tesla-spacex", "tesla-spacex merger", "speculation of a potential"],
    "Market Share": ["target of rs", "passenger vehicles target"],
    "Innovation": ["potential tesla-spacex", "smart glasses", "halts worker tracking", "wins etauto", "ev technology of the year"],
    "Customer Satisfaction": ["satisfaction", "reviews"],
    "Safety Recall": ["recall", "defect"],
    "Competition": ["rivian says", "competitor", "tore apart", "launches cheaper"],
    "Electric Vehicles": ["tore apart", "secures over", "electric cv", "wins etauto", "ev technology"],
    "Autonomous Driving": ["self-driving", "self driving", "fsd", "autopilot", "robotaxi", "autonomous driving"],
    "Energy Storage": ["megapack", "powerwall"]
}

def generate_explainability_data(text: str, topic_name: str, score: float, threshold: float, rank: int, all_labels: List[str], all_scores: List[str]) -> dict:
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    keywords = TOPIC_KEYWORDS.get(topic_name, [])
    
    supporting_sentence = ""
    supporting_keywords = []
    
    # Find supporting keywords actually in text
    text_lower = text.lower()
    for kw in keywords:
        if kw in text_lower:
            supporting_keywords.append(kw)
            
    # Find best supporting sentence based on keyword density
    best_density = -1
    for sent in sentences:
        sent_lower = sent.lower()
        density = sum(1 for kw in keywords if kw in sent_lower)
        if density > best_density and density > 0:
            best_density = density
            supporting_sentence = sent
            
    # Fallback supporting sentence if none matched keywords
    if not supporting_sentence and sentences:
        supporting_sentence = sentences[0]
        
    # Competing rejected topics (score < threshold but >= 0.15)
    rejected_competing = []
    for l, s in zip(all_labels, all_scores):
        if l != topic_name and s >= 0.15:
            rejected_competing.append({"topic": l, "confidence": round(float(s), 4)})
            
    # Decision reason
    reason = f"Confidence score {round(score, 4)} exceeded the calibrated threshold of {threshold}."
    if supporting_keywords:
        reason += f" Supporting keywords found: {', '.join(supporting_keywords[:3])}."
        
    return {
        "topic": topic_name,
        "confidence": round(float(score), 4),
        "threshold": threshold,
        "supporting_sentence": supporting_sentence,
        "supporting_keywords": supporting_keywords,
        "ranking_position": rank,
        "rejected_competing_topics": rejected_competing[:3],
        "decision_reason": reason
    }

# ─────────────────────────────────────────────────────────────
# CORRELATED LOGGING UTILITY — Matches Entity Matching Logger
# ─────────────────────────────────────────────────────────────

class CorrelatedLogger:
    def __init__(self, name: str, context: Optional[Dict[str, Any]] = None):
        self.name = name
        self.context = context or {}
        self._logger = logging.getLogger(name)

    def bind(self, **kwargs) -> 'CorrelatedLogger':
        return CorrelatedLogger(self.name, {**self.context, **kwargs})

    def _format(self, event: str, **kwargs) -> str:
        all_ctx = {**self.context, **kwargs}
        all_ctx["event"] = event
        all_ctx["ts"] = datetime.now(timezone.utc).isoformat()
        
        # Sort keys to make logs perfectly predictable and clean
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
logger = CorrelatedLogger("topic_classification.batch_processor")

# ─────────────────────────────────────────────────────────────
# TOPIC PROCESSING STATES — Phase H6
# ─────────────────────────────────────────────────────────────

class TopicProcessingState:
    PENDING    = "PENDING"
    PROCESSING = "PROCESSING"
    TOPIC_CLASSIFIED = "TOPIC_CLASSIFIED"
    FAILED     = "FAILED"
    RETRYING   = "RETRYING"
    SKIPPED    = "SKIPPED"
    COMPLETED  = "COMPLETED"  # Legacy/final completed compatibility

    TRANSITIONS = {
        PENDING:          {PROCESSING, SKIPPED, RETRYING, FAILED},
        PROCESSING:       {TOPIC_CLASSIFIED, FAILED, SKIPPED, RETRYING, COMPLETED},
        RETRYING:         {PROCESSING, RETRYING, FAILED},
        FAILED:           {PROCESSING},   # Allow resuming from FAILED
        TOPIC_CLASSIFIED: set(),          # Terminal
        SKIPPED:          {PROCESSING},   # Allow reprocessing skipped
        COMPLETED:        set()           # Terminal
    }

    @classmethod
    def is_valid_transition(cls, from_state: str, to_state: str) -> bool:
        allowed = cls.TRANSITIONS.get(from_state, set())
        return to_state in allowed

# ─────────────────────────────────────────────────────────────
# RETRY CONFIGURATION
#
# See RetryConfig's comment in entity_matching_batch_processor.py for the
# full 4-pattern retry/backoff inventory (FINDINGS.md #18). This is pattern
# 3 of 4 -- an in-process retry state machine, mirrored by RetryConfig and
# SentimentRetryConfig.
# ─────────────────────────────────────────────────────────────

@dataclass
class TopicRetryConfig:
    max_retries: int = 3
    base_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 60.0
    permanent_failure_patterns: List[str] = None

    def __post_init__(self):
        if self.permanent_failure_patterns is None:
            self.permanent_failure_patterns = [
                "UnicodeDecodeError",
                "document_not_found",
                "ValueError",
                "AttributeError"
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

class TopicDocumentStateMachine:
    """
    Manages atomic document state transitions in PostgreSQL for Topic Classification.
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

        current = doc.topic_processing_status or TopicProcessingState.PENDING
        if not TopicProcessingState.is_valid_transition(current, to_state):
            raise ValueError(
                f"Invalid state transition: {current} -> {to_state} for document {document_id}"
            )

        doc.topic_processing_status = to_state
        if run_id is not None:
            doc.topic_run_id = run_id
        if batch_id is not None:
            doc.topic_batch_id = batch_id
        if failure_reason is not None:
            doc.topic_failure_reason = str(failure_reason)[:4000]
        if retry_count is not None:
            doc.topic_retry_count = retry_count
        if processing_time_ms is not None:
            doc.topic_processing_time_ms = processing_time_ms
        if to_state == TopicProcessingState.FAILED:
            doc.topic_failed_at = datetime.now(timezone.utc)

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
            ok = TopicDocumentStateMachine.transition(
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
# HARDENED TOPIC BATCH PROCESSOR
# ─────────────────────────────────────────────────────────────

@dataclass
class TopicDocumentResult:
    document_id: str
    state: str
    topics_written: int = 0
    topics_rejected: int = 0
    processing_time_ms: float = 0.0
    retry_count: int = 0
    failure_reason: Optional[str] = None
    exception_type: Optional[str] = None
    stack_trace: Optional[str] = None

@dataclass
class TopicBatchResult:
    run_id: str
    batch_id: str
    client_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_documents: int = 0
    classified: int = 0
    failed: int = 0
    skipped: int = 0
    retried: int = 0
    db_rollbacks: int = 0
    document_results: List[TopicDocumentResult] = None

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
            "classified": self.classified,
            "failed": self.failed,
            "skipped": self.skipped,
            "retried": self.retried,
            "db_rollbacks": self.db_rollbacks
        }

class HardenedTopicClassifier:
    """
    Production-grade, highly reliable Topic Classification engine.
    Ensures:
      - Per-document isolated transactions (Phase H2)
      - Stage isolation (Phase H1 - Topic failure NEVER stops sentiment or pipeline)
      - Concurrency & duplicate write protection via UPSERT ON CONFLICT DO NOTHING (Phase H3)
      - Detailed structured logging with full correlation context (Phase H4)
      - Transient/permanent retry isolation with exponential backoff (Phase H5)
      - Deterministic state machine transitions (Phase H6)
    """
    def __init__(
        self,
        classifier_instance,  # We pass the underlying transformers/mock Classifier
        retry_config: Optional[TopicRetryConfig] = None,
        worker_id: Optional[str] = None
    ):
        self.classifier = classifier_instance
        self.retry_config = retry_config or TopicRetryConfig()
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"

    def _process_single_document_in_transaction(
        self,
        document_id: str,
        run_id: str,
        batch_id: str,
        client_id: str,
        doc_logger: CorrelatedLogger,
        threshold: float = 0.5
    ) -> TopicDocumentResult:
        start_time = time.perf_counter()
        db = SessionLocal()

        try:
            # Pre-flight state check
            doc_check = db.query(Document).filter(Document.id == document_id).first()
            if doc_check and doc_check.topic_processing_status in {TopicProcessingState.TOPIC_CLASSIFIED, TopicProcessingState.COMPLETED, TopicProcessingState.SKIPPED}:
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                doc_logger.info("document_skipped_already_processed",
                                document_id=document_id,
                                current_state=doc_check.topic_processing_status)
                return TopicDocumentResult(
                    document_id=document_id,
                    state=TopicProcessingState.SKIPPED,
                    processing_time_ms=elapsed
                )

            # STEP 1: Set state to PROCESSING (atomic, locks row)
            transition_ok = TopicDocumentStateMachine.transition(
                db, document_id, TopicProcessingState.PROCESSING,
                run_id=run_id, batch_id=batch_id
            )
            if not transition_ok:
                doc_logger.warning("document_not_found_skipping", document_id=document_id)
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                return TopicDocumentResult(
                    document_id=document_id,
                    state=TopicProcessingState.SKIPPED,
                    processing_time_ms=elapsed,
                    failure_reason="document_not_found"
                )

            # STEP 2: Load content & matched entities for preprocessing
            doc = db.query(Document).filter(Document.id == document_id).first()
            content = doc.normalized_content if doc else None

            if not doc or not content or not content.strip():
                doc.topic_processing_status = TopicProcessingState.SKIPPED
                doc.topic_failure_reason = "no_normalized_content"
                db.commit()
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                doc_logger.info("document_skipped_no_content", document_id=document_id)
                return TopicDocumentResult(
                    document_id=document_id,
                    state=TopicProcessingState.SKIPPED,
                    processing_time_ms=elapsed,
                    failure_reason="no_content"
                )

            # Query matched entity keywords for smart content extraction.
            # Reads from EntityMention (accuracy-gated) rather than the
            # ungated DocumentMatch table -- see FINDINGS.md.
            matches = db.query(EntityMention).filter(EntityMention.document_id == document_id).all()
            matched_keywords = set()
            for m in matches:
                ent = db.query(Entity).filter(Entity.id == m.entity_id).first()
                if ent:
                    matched_keywords.add(ent.name)

            # Run advanced preprocessing (Phase A2)
            preprocessed_text = preprocess_document_text(
                content,
                title=doc.title or "",
                summary="",
                matched_keywords=matched_keywords
            )
            if not preprocessed_text.strip():
                preprocessed_text = content

            # STEP 3: Load active topics taxonomy & per-topic thresholds (Phase A3)
            active_topics = db.query(Topic).filter(Topic.is_active == True).all()
            if not active_topics:
                doc.topic_processing_status = TopicProcessingState.SKIPPED
                doc.topic_failure_reason = "empty_taxonomy"
                db.commit()
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                doc_logger.warning("taxonomy_empty_skipping", document_id=document_id)
                return TopicDocumentResult(
                    document_id=document_id,
                    state=TopicProcessingState.SKIPPED,
                    processing_time_ms=elapsed,
                    failure_reason="empty_taxonomy"
                )

            topic_names = [t.name for t in active_topics]
            topic_map = {t.name: t.id for t in active_topics}
            topic_thresholds = {t.name: (t.confidence_threshold or 0.5) for t in active_topics}

            doc_logger.debug("classification_started", content_length=len(preprocessed_text))

            # STEP 4: Classify using the Zero-Shot model on the preprocessed text (Phase A2)
            try:
                results = self.classifier.classify_text(preprocessed_text, topic_names)
            except Exception as ml_exc:
                raise RuntimeError(f"Model classification failed: {ml_exc}") from ml_exc

            # STEP 5: Apply per-topic thresholds, negative suppression, and explainability (Phases A3, A4, A5)
            topics_written = 0
            topics_rejected = 0

            # Sort scores and labels descending to get rankings
            labels_scores = list(zip(results.get("labels", []), results.get("scores", [])))
            labels_scores.sort(key=lambda x: x[1], reverse=True)

            sorted_labels = [x[0] for x in labels_scores]
            sorted_scores = [x[1] for x in labels_scores]

            # Identify which topics pass their per-topic confidence threshold.
            # NOTE: this used to additionally require a literal TOPIC_KEYWORDS phrase
            # match ("high precision keyword gating"). Verified live against real
            # inference output (see FINDINGS.md P1-C): the model correctly and
            # confidently classifies the overwhelming majority of documents (scores
            # 0.5-0.99, well above the per-topic threshold), but TOPIC_KEYWORDS is a
            # small set of literal phrases reverse-engineered from a narrow sample
            # (e.g. "tapped by meta", "wins etauto") that essentially never recur
            # verbatim — the AND-gate was rejecting ~99% of correctly-classified
            # documents. Confidence threshold + apply_negative_suppression() below
            # (real disambiguation rules, e.g. Nikola Tesla vs. Tesla Inc.) remain as
            # the actual precision guards.
            passed_threshold_topics = []
            for label, score in labels_scores:
                thresh = topic_thresholds.get(label, 0.5)
                if score >= thresh:
                    passed_threshold_topics.append(label)
                else:
                    topics_rejected += 1

            # Apply negative suppression (Phase A4)
            final_topics = apply_negative_suppression(preprocessed_text, passed_threshold_topics)

            # Write accepted topics to DB with explainability metadata (Phase A5)
            for rank_idx, (label, score) in enumerate(labels_scores):
                if label in final_topics:
                    # Generate explainability metadata
                    explain_data = generate_explainability_data(
                        preprocessed_text,
                        label,
                        score,
                        topic_thresholds[label],
                        rank_idx + 1,
                        sorted_labels,
                        sorted_scores
                    )

                    stmt = insert(DocumentTopic).values(
                        id=uuid.uuid4(),
                        document_id=document_id,
                        topic_id=topic_map[label],
                        confidence_score=score,
                        explainability_metadata=explain_data
                    ).on_conflict_do_nothing(
                        index_elements=['document_id', 'topic_id']
                    )
                    db.execute(stmt)
                    topics_written += 1
                elif label in passed_threshold_topics:
                    # It passed threshold but was suppressed by negative rules
                    topics_rejected += 1

            # Log the model run audit record
            run_log = ModelRun(
                document_id=document_id,
                model_name=self.classifier.model_name,
                model_version=self.classifier.model_version
            )
            db.add(run_log)

            # STEP 6: Final transition to TOPIC_CLASSIFIED (committed atomically with topics)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            doc.topic_processing_status = TopicProcessingState.TOPIC_CLASSIFIED
            doc.topic_run_id = run_id
            doc.topic_batch_id = batch_id
            doc.topic_processing_time_ms = elapsed_ms
            doc.topic_failure_reason = None

            db.commit() # Atomic commit of topics, model run log, and state
            db.close()

            doc_logger.info("document_classified_successfully",
                            topics_written=topics_written,
                            topics_rejected=topics_rejected,
                            processing_time_ms=round(elapsed_ms, 2),
                            status="success")

            return TopicDocumentResult(
                document_id=document_id,
                state=TopicProcessingState.TOPIC_CLASSIFIED,
                topics_written=topics_written,
                topics_rejected=topics_rejected,
                processing_time_ms=elapsed_ms
            )

        except Exception as exc:
            # ROLLBACK isolated document transaction
            try:
                db.rollback()
            except Exception:
                pass
            finally:
                db.close()

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            exc_type = type(exc).__name__
            exc_reason = str(exc)[:2000]
            stack = traceback.format_exc()

            doc_logger.error("document_classification_failed",
                             exception_type=exc_type,
                             failure_reason=exc_reason,
                             processing_time_ms=round(elapsed_ms, 2),
                             stack_trace=stack[:2000],
                             status="error")

            return TopicDocumentResult(
                document_id=document_id,
                state=TopicProcessingState.FAILED,
                processing_time_ms=elapsed_ms,
                failure_reason=exc_reason,
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
        doc_logger: CorrelatedLogger,
        threshold: float = 0.5
    ) -> TopicDocumentResult:
        result = self._process_single_document_in_transaction(
            document_id, run_id, batch_id, client_id, doc_logger, threshold
        )

        if result.state == TopicProcessingState.FAILED:
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
                TopicDocumentStateMachine.transition_and_commit(
                    document_id, TopicProcessingState.RETRYING,
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
                    document_id, run_id, batch_id, client_id, retry_logger, threshold
                )
                retried_result.retry_count = new_retry_count
                return retried_result

            else:
                doc_logger.error("document_permanently_failed",
                                 retry_count=current_retry_count,
                                 is_permanent=is_permanent,
                                 failure_reason=result.failure_reason)

                # Persist terminal FAILED state in a separate session
                TopicDocumentStateMachine.transition_and_commit(
                    document_id, TopicProcessingState.FAILED,
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
        threshold: float = 0.5,
        batch_size: int = 16
    ) -> TopicBatchResult:
        run_id = uuid.uuid4().hex
        batch_id = batch_id or uuid.uuid4().hex[:12]

        batch_logger = logger.bind(
            run_id=run_id,
            batch_id=batch_id,
            client_id=client_id,
            worker_id=self.worker_id,
            processing_stage="topic_classification"
        )

        batch_result = TopicBatchResult(
            run_id=run_id,
            batch_id=batch_id,
            client_id=client_id,
            started_at=datetime.now(timezone.utc),
            total_documents=len(document_ids)
        )

        batch_logger.info("batch_started",
                          total_documents=len(document_ids),
                          max_retries=self.retry_config.max_retries,
                          batch_size=batch_size)

        # STAGE 1: Preparation (Isolated Rows Locking, State transition & Preprocessing)
        prepared_docs = []
        for idx, document_id in enumerate(document_ids):
            doc_logger = batch_logger.bind(
                document_id=document_id,
                doc_index=idx + 1,
                doc_total=len(document_ids)
            )

            db = SessionLocal()
            try:
                # Lock row and transition to PROCESSING
                transition_ok = TopicDocumentStateMachine.transition(
                    db, document_id, TopicProcessingState.PROCESSING,
                    run_id=run_id, batch_id=batch_id
                )
                if not transition_ok:
                    db.close()
                    batch_result.document_results.append(TopicDocumentResult(
                        document_id=document_id,
                        state=TopicProcessingState.SKIPPED,
                        failure_reason="document_not_found"
                    ))
                    batch_result.skipped += 1
                    continue

                doc = db.query(Document).filter(Document.id == document_id).first()
                content = doc.normalized_content if doc else None
                title = doc.title or ""

                if not doc or not content or not content.strip():
                    doc.topic_processing_status = TopicProcessingState.SKIPPED
                    doc.topic_failure_reason = "no_normalized_content"
                    db.commit()
                    db.close()
                    batch_result.document_results.append(TopicDocumentResult(
                        document_id=document_id,
                        state=TopicProcessingState.SKIPPED,
                        failure_reason="no_content"
                    ))
                    batch_result.skipped += 1
                    continue

                # Query matched entity keywords for smart content extraction.
                # Reads from EntityMention (accuracy-gated) rather than the
                # ungated DocumentMatch table -- see FINDINGS.md.
                matches = db.query(EntityMention).filter(EntityMention.document_id == document_id).all()
                matched_keywords = set()
                for m in matches:
                    ent = db.query(Entity).filter(Entity.id == m.entity_id).first()
                    if ent:
                        matched_keywords.add(ent.name)

                db.commit() # Commit state transition
                db.close()

                # Run advanced preprocessing (Phase A2)
                preprocessed_text = preprocess_document_text(
                    content,
                    title=title,
                    summary="",
                    matched_keywords=matched_keywords
                )
                if not preprocessed_text.strip():
                    preprocessed_text = content

                prepared_docs.append({
                    "id": document_id,
                    "preprocessed_text": preprocessed_text,
                    "logger": doc_logger
                })

            except Exception as prep_exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                finally:
                    db.close()

                # Transition to FAILED
                TopicDocumentStateMachine.transition_and_commit(
                    document_id, TopicProcessingState.FAILED,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason=f"Preparation failed: {str(prep_exc)}"
                )
                batch_result.document_results.append(TopicDocumentResult(
                    document_id=document_id,
                    state=TopicProcessingState.FAILED,
                    failure_reason=str(prep_exc)
                ))
                batch_result.failed += 1

        if not prepared_docs:
            batch_result.completed_at = datetime.now(timezone.utc)
            batch_logger.info("batch_completed", **batch_result.summary())
            return batch_result

        # STAGE 2: Batch Inference (Fast parallel model forward passes)
        texts_to_classify = [d["preprocessed_text"] for d in prepared_docs]

        db = SessionLocal()
        try:
            # Load active topics once for the entire batch
            active_topics = db.query(Topic).filter(Topic.is_active == True).all()
            topic_names = [t.name for t in active_topics]
            topic_map = {t.name: t.id for t in active_topics}
            topic_thresholds = {t.name: (t.confidence_threshold or 0.5) for t in active_topics}
        finally:
            db.close()

        if not active_topics:
            for p in prepared_docs:
                TopicDocumentStateMachine.transition_and_commit(
                    p["id"], TopicProcessingState.SKIPPED,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason="empty_taxonomy"
                )
                batch_result.document_results.append(TopicDocumentResult(
                    document_id=p["id"],
                    state=TopicProcessingState.SKIPPED,
                    failure_reason="empty_taxonomy"
                ))
                batch_result.skipped += 1
            batch_result.completed_at = datetime.now(timezone.utc)
            batch_logger.info("batch_completed", **batch_result.summary())
            return batch_result

        try:
            # Call our new pipeline batch classification
            batch_results = self.classifier.classify_batch(texts_to_classify, topic_names, batch_size=batch_size)
        except Exception as inf_exc:
            for p in prepared_docs:
                TopicDocumentStateMachine.transition_and_commit(
                    p["id"], TopicProcessingState.FAILED,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason=f"Batch inference failed: {str(inf_exc)}"
                )
                batch_result.document_results.append(TopicDocumentResult(
                    document_id=p["id"],
                    state=TopicProcessingState.FAILED,
                    failure_reason=str(inf_exc)
                ))
                batch_result.failed += 1
            batch_result.completed_at = datetime.now(timezone.utc)
            batch_logger.info("batch_completed", **batch_result.summary())
            return batch_result

        # STAGE 3: Database Writes & Completion (Isolated per document for transaction safety)
        for p, res in zip(prepared_docs, batch_results):
            doc_id = p["id"]
            preprocessed_text = p["preprocessed_text"]
            doc_logger = p["logger"]

            t_start = time.perf_counter()
            db = SessionLocal()
            try:
                # Lock row
                doc = db.query(Document).filter(Document.id == doc_id).with_for_update().first()

                # Sort scores and labels
                labels_scores = list(zip(res.get("labels", []), res.get("scores", [])))
                labels_scores.sort(key=lambda x: x[1], reverse=True)

                sorted_labels = [x[0] for x in labels_scores]
                sorted_scores = [x[1] for x in labels_scores]

                # Apply per-topic confidence thresholds. See FINDINGS.md P1-C: the
                # literal TOPIC_KEYWORDS "high precision keyword gating" AND-gate
                # previously here rejected ~99% of correctly, confidently classified
                # documents (verified against real model output) because its phrases
                # were reverse-engineered from a narrow sample and essentially never
                # recur verbatim. apply_negative_suppression() below remains as the
                # real precision guard.
                passed_threshold_topics = []
                topics_rejected = 0
                for label, score in labels_scores:
                    thresh = topic_thresholds.get(label, 0.5)
                    if score >= thresh:
                        passed_threshold_topics.append(label)
                    else:
                        topics_rejected += 1

                # Apply negative suppression
                final_topics = apply_negative_suppression(preprocessed_text, passed_threshold_topics)

                # Write accepted topics to DB with explainability metadata
                topics_written = 0
                for rank_idx, (label, score) in enumerate(labels_scores):
                    if label in final_topics:
                        explain_data = generate_explainability_data(
                            preprocessed_text,
                            label,
                            score,
                            topic_thresholds[label],
                            rank_idx + 1,
                            sorted_labels,
                            sorted_scores
                        )

                        stmt = insert(DocumentTopic).values(
                            id=uuid.uuid4(),
                            document_id=doc_id,
                            topic_id=topic_map[label],
                            confidence_score=score,
                            explainability_metadata=explain_data
                        ).on_conflict_do_nothing(
                            index_elements=['document_id', 'topic_id']
                        )
                        db.execute(stmt)
                        topics_written += 1

                # Log model run
                run_log = ModelRun(
                    document_id=doc_id,
                    model_name=self.classifier.model_name,
                    model_version=self.classifier.model_version
                )
                db.add(run_log)

                # Transition to TOPIC_CLASSIFIED
                elapsed_ms = (time.perf_counter() - t_start) * 1000
                doc.topic_processing_status = TopicProcessingState.TOPIC_CLASSIFIED
                doc.topic_run_id = run_id
                doc.topic_batch_id = batch_id
                doc.topic_processing_time_ms = elapsed_ms
                doc.topic_failure_reason = None

                db.commit()
                db.close()

                batch_result.document_results.append(TopicDocumentResult(
                    document_id=doc_id,
                    state=TopicProcessingState.TOPIC_CLASSIFIED,
                    topics_written=topics_written,
                    topics_rejected=topics_rejected,
                    processing_time_ms=elapsed_ms
                ))
                batch_result.classified += 1

            except Exception as doc_exc:
                try:
                    db.rollback()
                except Exception:
                    pass
                finally:
                    db.close()

                # Transition to FAILED
                TopicDocumentStateMachine.transition_and_commit(
                    doc_id, TopicProcessingState.FAILED,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason=str(doc_exc)
                )
                batch_result.document_results.append(TopicDocumentResult(
                    document_id=doc_id,
                    state=TopicProcessingState.FAILED,
                    failure_reason=str(doc_exc)
                ))
                batch_result.failed += 1

        batch_result.completed_at = datetime.now(timezone.utc)
        batch_logger.info("batch_completed", **batch_result.summary())
        return batch_result
