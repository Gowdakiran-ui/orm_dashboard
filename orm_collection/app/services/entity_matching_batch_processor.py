"""
Entity Matching Batch Processor - Phase 1.1 Hardened Implementation

Implements:
  Phase B: Per-document failure isolation
  Phase C: Document processing state machine
  Phase D: Retry strategy with exponential backoff
  Phase E: Per-document transaction safety
  Phase F: Correlation IDs on every execution
  Phase G: Structured logging on every log line

DOES NOT MODIFY:
  FlashText matching logic, spaCy NER logic,
  confidence scoring, or any matching algorithm.

Bug Fixes Applied (Phase A Audit):
  W1: File corruption/syntax error - complete clean rewrite
  W2: PROCESSING state no longer pre-committed before matches
  W3: FAILED->PROCESSING transition added to state machine
  W4: Stuck PROCESSING docs recovered at process_client startup
  W5: get_resumable_documents() self-referential subquery fixed
  W6: COMPLETED added as recognised legacy terminal state
  W9: Stack traces preserved in full
  W10: Whitespace-only content detected and skipped
"""

import uuid
import time
import traceback
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.document import Document, DocumentMatch
from app.models.entity import Entity
from app.services.matching_engine import engine_instance


# Phase G - Structured correlated logger
class CorrelatedLogger:
    """
    Structured logger that automatically prepends correlation context
    to every log line. Uses stdlib logging - no external dependencies.
    Fields automatically included: run_id, batch_id, client_id,
    document_id, worker_id, processing_stage.
    """
    def __init__(self, name: str = "entity_matching"):
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S"
            ))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.DEBUG)
        self._context: Dict[str, Any] = {}

    def bind(self, **kwargs) -> "CorrelatedLogger":
        """Return a new logger with additional context bound."""
        new = CorrelatedLogger.__new__(CorrelatedLogger)
        new._logger = self._logger
        new._context = {**self._context, **kwargs}
        return new

    def _format(self, event: str, **kwargs) -> str:
        ctx = {**self._context, "event": event, **kwargs,
               "ts": datetime.now(timezone.utc).isoformat()}
        parts = [f"{k}={json.dumps(v, default=str)}" for k, v in ctx.items()]
        return " | ".join(parts)

    def info(self, event: str, **kwargs):
        self._logger.info(self._format(event, **kwargs))

    def debug(self, event: str, **kwargs):
        self._logger.debug(self._format(event, **kwargs))

    def warning(self, event: str, **kwargs):
        self._logger.warning(self._format(event, **kwargs))

    def error(self, event: str, **kwargs):
        self._logger.error(self._format(event, **kwargs))


logger = CorrelatedLogger("entity_matching.batch_processor")


# Phase C - Processing states
class ProcessingState:
    PENDING    = "PENDING"
    PROCESSING = "PROCESSING"
    MATCHED    = "MATCHED"
    FAILED     = "FAILED"
    SKIPPED    = "SKIPPED"
    RETRYING   = "RETRYING"
    COMPLETED  = "COMPLETED"   # W6: legacy terminal state
    AMBIGUOUS  = "AMBIGUOUS"   # Phase 1.2: Ambiguous matches

    # Valid state transitions
    TRANSITIONS = {
        "PENDING":    {"PROCESSING", "SKIPPED"},
        "PROCESSING": {"MATCHED", "FAILED", "SKIPPED", "RETRYING", "AMBIGUOUS"},
        "RETRYING":   {"PROCESSING"},
        "FAILED":     {"PROCESSING"},   # W3: resume from FAILED
        "MATCHED":    set(),
        "SKIPPED":    {"PROCESSING"},
        "COMPLETED":  set(),            # W6: legacy terminal
        "AMBIGUOUS":  {"PROCESSING"},   # Allow resuming from AMBIGUOUS if rules/config change
    }

    # States considered done - skip without reprocessing
    TERMINAL_DONE = {"MATCHED", "SKIPPED", "COMPLETED"}

    @classmethod
    def is_valid_transition(cls, from_state: str, to_state: str) -> bool:
        allowed = cls.TRANSITIONS.get(from_state, set())
        return to_state in allowed

    @classmethod
    def is_resumable(cls, state: str) -> bool:
        return state in {cls.FAILED, cls.RETRYING, cls.PENDING}

    @classmethod
    def is_terminal(cls, state: str) -> bool:
        return not cls.TRANSITIONS.get(state, None)


# Phase D - Retry configuration
@dataclass
class RetryConfig:
    max_retries: int = 3
    base_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 60.0
    permanent_failure_patterns: List[str] = field(default_factory=lambda: [
        "UnicodeDecodeError",
        "document_not_found",
    ])

    def backoff_seconds(self, retry_count: int) -> float:
        """Exponential backoff: base * 2^retry, capped at max."""
        delay = self.base_backoff_seconds * (2 ** retry_count)
        return min(delay, self.max_backoff_seconds)

    def is_permanent_failure(self, exception_type: str, failure_reason: str) -> bool:
        for pattern in self.permanent_failure_patterns:
            if pattern in exception_type or pattern in failure_reason:
                return True
        return False


@dataclass
class DocumentResult:
    document_id: str
    state: str
    matches_written: int = 0
    processing_time_ms: float = 0.0
    retry_count: int = 0
    failure_reason: Optional[str] = None
    exception_type: Optional[str] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BatchResult:
    run_id: str
    batch_id: str
    client_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_documents: int = 0
    matched: int = 0
    failed: int = 0
    skipped: int = 0
    ambiguous: int = 0  # Phase 1.2
    retried: int = 0
    db_rollbacks: int = 0
    duplicate_writes_prevented: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    document_results: List[DocumentResult] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        elapsed = (self.completed_at - self.started_at).total_seconds() if self.completed_at else 0
        return {
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "client_id": self.client_id,
            "elapsed_seconds": round(elapsed, 2),
            "total": self.total_documents,
            "matched": self.matched,
            "failed": self.failed,
            "skipped": self.skipped,
            "ambiguous": self.ambiguous,
            "retried": self.retried,
            "db_rollbacks": self.db_rollbacks,
            "duplicate_writes_prevented": self.duplicate_writes_prevented,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
        }


# Phase C & E - State machine with atomic transitions
class DocumentStateMachine:
    """
    Manages atomic document state transitions in PostgreSQL.

    W2 FIX: transition() sets state in-memory only. Caller commits atomically
    with match records. For post-rollback state writes, use transition_and_commit()
    which opens its own isolated session.
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
        """
        Set document state in-memory within caller's transaction.
        Does NOT commit. Caller decides when to commit.
        Returns True if found and set; False if not found.
        Raises ValueError for invalid transitions.
        """
        doc = db.query(Document).filter(
            Document.id == document_id
        ).with_for_update().first()
        if not doc:
            return False

        current = doc.processing_status or ProcessingState.PENDING
        if not ProcessingState.is_valid_transition(current, to_state):
            raise ValueError(
                f"Invalid state transition: {current} -> {to_state} "
                f"for document {document_id}"
            )

        doc.processing_status = to_state
        if run_id is not None:
            doc.match_run_id = run_id
        if batch_id is not None:
            doc.match_batch_id = batch_id
        if failure_reason is not None:
            doc.match_failure_reason = str(failure_reason)[:4000]
        if retry_count is not None:
            doc.match_retry_count = retry_count
        if processing_time_ms is not None:
            doc.match_processing_time_ms = processing_time_ms
        if to_state == ProcessingState.FAILED:
            doc.match_failed_at = datetime.now(timezone.utc)

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
        """
        Open a dedicated session, set state, and commit immediately.
        Used for FAILED/RETRYING state after a transaction rollback.
        """
        db = SessionLocal()
        try:
            ok = DocumentStateMachine.transition(
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

    @staticmethod
    def get_documents_for_client(
        db: Session, client_id: str, limit: int = 500
    ) -> List[Document]:
        """
        Get all processable documents for a client.
        Includes PENDING, FAILED, RETRYING, and PROCESSING (W4: crash recovery).
        """
        from app.models.entity import Entity
        entity_ids = db.query(Entity.id).filter(
            Entity.client_id == client_id
        ).scalar_subquery()
        matched_doc_ids = (
            db.query(DocumentMatch.document_id)
            .filter(DocumentMatch.matched_entity_id.in_(entity_ids))
            .scalar_subquery()
        )
        return (
            db.query(Document)
            .filter(Document.id.in_(matched_doc_ids))
            .filter(Document.processing_status.in_([
                ProcessingState.PENDING,
                ProcessingState.FAILED,
                ProcessingState.RETRYING,
                ProcessingState.PROCESSING,
            ]))
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_resumable_documents(
        db: Session, client_id: str, limit: int = 500
    ) -> List[Document]:
        """
        W5 FIX: Correct entity join - no self-referential subquery.
        Returns PENDING, FAILED, RETRYING docs for a client.
        """
        from app.models.entity import Entity
        entity_ids = db.query(Entity.id).filter(
            Entity.client_id == client_id
        ).scalar_subquery()
        matched_doc_ids = (
            db.query(DocumentMatch.document_id)
            .filter(DocumentMatch.matched_entity_id.in_(entity_ids))
            .scalar_subquery()
        )
        return (
            db.query(Document)
            .filter(Document.id.in_(matched_doc_ids))
            .filter(Document.processing_status.in_([
                ProcessingState.PENDING,
                ProcessingState.FAILED,
                ProcessingState.RETRYING,
            ]))
            .limit(limit)
            .all()
        )


class EntityMatchingBatchProcessor:
    """
    Production-grade entity matching batch processor.

    Guarantees (Phase 1.1 Hardening):
      One document failure NEVER stops the batch (Phase B)
      Every document has a deterministic processing state (Phase C)
      Failed documents can resume safely (Phase C/D)
      Every document executes inside its own transaction (Phase E)
      No partial writes are possible (Phase E)
      Every execution is fully traceable via correlation IDs (Phase F)
      Logs are structured and production-grade (Phase G)
      Retry logic is deterministic and verifiable (Phase D)
    """

    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        worker_id: Optional[str] = None,
    ):
        self.retry_config = retry_config or RetryConfig()
        self.worker_id = worker_id or uuid.uuid4().hex[:8]

    # Phase E - Per-document transaction
    def _process_single_document_in_transaction(
        self,
        document_id: str,
        run_id: str,
        batch_id: str,
        client_id: str,
        doc_logger: CorrelatedLogger,
    ) -> DocumentResult:
        """
        Execute entity matching for ONE document inside its own transaction.

        W2 fix: PROCESSING state is set in-memory and committed ATOMICALLY
        with match records in a single db.commit(). No pre-commit of state.

        Transaction scope:
          BEGIN
            Set PROCESSING (in-memory)
            Load document content
            Run matching engine (read-only)
            db.add_all(matches)
            Set MATCHED (in-memory)
          COMMIT - both matches and state together

        On any exception:
          ROLLBACK - nothing written
          FAILED state written in a separate dedicated session
        """
        start_time = time.perf_counter()
        db = SessionLocal()

        try:
            # Pre-flight: skip terminal states
            doc_check = db.query(Document).filter(
                Document.id == document_id
            ).first()
            if doc_check and doc_check.processing_status in ProcessingState.TERMINAL_DONE:
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                doc_logger.info("document_skipped_already_processed",
                                document_id=document_id,
                                current_state=doc_check.processing_status)
                return DocumentResult(
                    document_id=document_id,
                    state=ProcessingState.SKIPPED,
                    processing_time_ms=elapsed,
                )

            # STEP 1: Set PROCESSING in-memory (NOT committed - W2 fix)
            transition_ok = DocumentStateMachine.transition(
                db, document_id, ProcessingState.PROCESSING,
                run_id=run_id, batch_id=batch_id
            )
            if not transition_ok:
                doc_logger.warning("document_not_found_skipping",
                                   document_id=document_id)
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                return DocumentResult(
                    document_id=document_id,
                    state=ProcessingState.SKIPPED,
                    processing_time_ms=elapsed,
                    failure_reason="document_not_found",
                )

            # STEP 2: Load document content
            doc = db.query(Document).filter(Document.id == document_id).first()
            content = doc.normalized_content if doc else None

            # W10 fix: reject whitespace-only content
            if not doc or not content or not content.strip():
                doc.processing_status = ProcessingState.SKIPPED
                doc.match_failure_reason = "no_normalized_content"
                db.commit()
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                doc_logger.info("document_skipped_no_content",
                                document_id=document_id)
                return DocumentResult(
                    document_id=document_id,
                    state=ProcessingState.SKIPPED,
                    processing_time_ms=elapsed,
                    failure_reason="no_normalized_content",
                )

            doc_logger.debug("document_processing_started",
                             title=doc.title[:80] if doc.title else "",
                             content_length=len(content))

            # STEP 3: Idempotency guard
            existing_matches = db.query(DocumentMatch).filter(
                DocumentMatch.document_id == document_id
            ).count()
            if existing_matches > 0:
                doc.processing_status = ProcessingState.MATCHED
                doc.match_run_id = run_id
                doc.match_batch_id = batch_id
                doc.match_processing_time_ms = 0.0
                doc.match_failure_reason = None
                db.commit()
                db.close()
                elapsed = (time.perf_counter() - start_time) * 1000
                doc_logger.info("document_skipped_already_matched",
                                document_id=document_id,
                                existing_matches=existing_matches)
                return DocumentResult(
                    document_id=document_id,
                    state=ProcessingState.MATCHED,
                    matches_written=existing_matches,
                    processing_time_ms=elapsed,
                )

            # STEP 4: Ensure matching engine is loaded
            if not engine_instance.is_loaded:
                engine_instance.refresh_processor(db)
                doc_logger.info("matching_engine_refreshed",
                                worker_id=self.worker_id)

            # STEP 5: Run matching (read-only, no DB writes)
            try:
                matches = engine_instance.find_matches(content)
            except Exception as match_exc:
                raise RuntimeError(
                    f"matching_engine_failed: {match_exc}"
                ) from match_exc

            # STEP 5.5: Run accuracy scoring and context evaluation for matches
            # Load entities involved to get their domain & name for scoring
            entity_ids_in_matches = list({m["entity_id"] for m in matches})
            entities_by_id = {}
            if entity_ids_in_matches:
                db_entities = db.query(Entity).filter(Entity.id.in_(entity_ids_in_matches)).all()
                entities_by_id = {str(e.id): e for e in db_entities}

            evaluated_matches = []
            for m in matches:
                entity = entities_by_id.get(m["entity_id"])
                domain = entity.domain if entity else None
                name = entity.name if entity else None
                metadata = engine_instance.evaluate_match_accuracy(content, m, entity_domain=domain, entity_name=name)
                
                # Copy match dict and attach evaluated confidence and metadata
                m_copy = dict(m)
                m_copy["confidence"] = metadata["final_confidence"]
                m_copy["metadata"] = metadata
                evaluated_matches.append(m_copy)

            # STEP 5.6: Ambiguity Delta Resolution
            # Group by matched span to detect overlaps/competing candidates
            span_groups = {}
            for m in evaluated_matches:
                span_key = (m["start_idx"], m["end_idx"])
                if span_key not in span_groups:
                    span_groups[span_key] = []
                span_groups[span_key].append(m)

            is_ambiguous_doc = False
            rejection_reasons = []

            for span_key, span_matches in span_groups.items():
                if len(span_matches) > 1:
                    # Sort by confidence descending
                    span_matches.sort(key=lambda x: x["confidence"], reverse=True)
                    top_match = span_matches[0]
                    second_match = span_matches[1]
                    delta = top_match["confidence"] - second_match["confidence"]
                    
                    if delta <= engine_instance.config.ambiguity_delta:
                        # Mark document as ambiguous
                        is_ambiguous_doc = True
                        rejection_reasons.append(
                            f"Ambiguity detected at span {span_key}: competing candidates "
                            f"'{top_match['matched_keyword']}' (conf: {top_match['confidence']}) and "
                            f"'{second_match['matched_keyword']}' (conf: {second_match['confidence']}) "
                            f"with delta {round(delta, 2)} <= {engine_instance.config.ambiguity_delta}"
                        )
                        # Set metadata to reflect ambiguous state
                        for sm in span_matches:
                            sm["metadata"]["status"] = "ambiguous"
                            sm["metadata"]["rejection_reasons"].append("Rejected due to ambiguity delta limit")

            # STEP 6: Deduplicate and build DB records
            # We save BOTH accepted and rejected/ambiguous matches for auditing (rejected ones have status in metadata)
            # Only accepted ones count for positive matches. If the document is ambiguous, we'll write matches with status='ambiguous'.
            unique_entities: Dict[str, Any] = {}
            for m in evaluated_matches:
                eid = m["entity_id"]
                # Keep the highest confidence match for each entity
                if eid not in unique_entities or m["confidence"] > unique_entities[eid]["confidence"]:
                    unique_entities[eid] = m

            db_matches = [
                DocumentMatch(
                    document_id=document_id,
                    matched_entity_id=m["entity_id"],
                    match_type=m["match_type"],
                    match_confidence=m["confidence"],
                    matched_text=m["matched_keyword"],
                    match_metadata=m["metadata"],
                )
                for m in unique_entities.values()
            ]

            # STEP 7: Atomic write - matches + state in ONE commit (W2)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if db_matches:
                db.add_all(db_matches)

            # Transition document to MATCHED or AMBIGUOUS
            final_state = ProcessingState.AMBIGUOUS if is_ambiguous_doc else ProcessingState.MATCHED
            
            # If no matches passed the confidence threshold, and not ambiguous, it might be SKIPPED or still MATCHED with 0 matches
            # Let's check if there is at least one accepted match
            has_accepted_match = any(m["metadata"]["status"] == "accepted" for m in unique_entities.values())
            if not is_ambiguous_doc and not has_accepted_match:
                final_state = ProcessingState.SKIPPED
                doc.match_failure_reason = "No matches passed the confidence threshold"
            
            doc.processing_status = final_state
            doc.match_run_id = run_id
            doc.match_batch_id = batch_id
            doc.match_processing_time_ms = elapsed_ms
            if final_state == ProcessingState.AMBIGUOUS:
                doc.match_failure_reason = "; ".join(rejection_reasons)[:4000]
            elif final_state == ProcessingState.MATCHED:
                doc.match_failure_reason = None

            db.commit()  # Both matches AND status atomically

            doc_logger.info("document_processed_successfully",
                            document_id=document_id,
                            final_state=final_state,
                            matches_written=len(db_matches),
                            processing_time_ms=round(elapsed_ms, 2))

            return DocumentResult(
                document_id=document_id,
                state=final_state,
                matches_written=len([d for d in db_matches if d.match_metadata["status"] == "accepted"]),
                processing_time_ms=elapsed_ms,
            )

        except Exception as exc:
            # ROLLBACK entire document transaction
            try:
                db.rollback()
            except Exception:
                pass

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            exc_type = type(exc).__name__
            exc_reason = str(exc)[:2000]
            stack = traceback.format_exc()  # W9 fix: full traceback

            doc_logger.error("document_matching_failed",
                             document_id=document_id,
                             exception_type=exc_type,
                             failure_reason=exc_reason,
                             processing_time_ms=round(elapsed_ms, 2),
                             stack_trace=stack[:2000])

            return DocumentResult(
                document_id=document_id,
                state=ProcessingState.FAILED,
                processing_time_ms=elapsed_ms,
                failure_reason=exc_reason,
                exception_type=exc_type,
                stack_trace=stack,
            )

        finally:
            try:
                db.close()
            except Exception:
                pass

    # Phase D - Retry logic
    def _process_with_retry(
        self,
        document_id: str,
        run_id: str,
        batch_id: str,
        client_id: str,
        current_retry_count: int,
        doc_logger: CorrelatedLogger,
    ) -> DocumentResult:
        """
        Process a single document with retry support.
        Every retry attempt is logged.
        Permanent failures are never retried.
        """
        result = self._process_single_document_in_transaction(
            document_id, run_id, batch_id, client_id, doc_logger
        )

        if result.state == ProcessingState.FAILED:
            is_permanent = self.retry_config.is_permanent_failure(
                result.exception_type or "",
                result.failure_reason or "",
            )
            can_retry = (
                not is_permanent
                and current_retry_count < self.retry_config.max_retries
            )

            if can_retry:
                new_retry_count = current_retry_count + 1
                backoff = self.retry_config.backoff_seconds(current_retry_count)

                doc_logger.info("document_retry_scheduled",
                                document_id=document_id,
                                retry_attempt=new_retry_count,
                                max_retries=self.retry_config.max_retries,
                                backoff_seconds=round(backoff, 2),
                                failure_reason=result.failure_reason)

                # Persist RETRYING in its own transaction (W2 fix)
                DocumentStateMachine.transition_and_commit(
                    document_id, ProcessingState.RETRYING,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason=result.failure_reason,
                    retry_count=new_retry_count,
                )

                time.sleep(backoff)

                retry_logger = doc_logger.bind(retry_count=new_retry_count)
                retry_logger.info("document_retry_attempt_started",
                                  document_id=document_id,
                                  retry_attempt=new_retry_count)

                retried_result = self._process_single_document_in_transaction(
                    document_id, run_id, batch_id, client_id, retry_logger,
                )
                retried_result.retry_count = new_retry_count
                return retried_result

            else:
                doc_logger.error("document_permanently_failed",
                                 document_id=document_id,
                                 retry_count=current_retry_count,
                                 is_permanent=is_permanent,
                                 failure_reason=result.failure_reason)

                # Persist FAILED in its own transaction (W2 fix)
                DocumentStateMachine.transition_and_commit(
                    document_id, ProcessingState.FAILED,
                    run_id=run_id, batch_id=batch_id,
                    failure_reason=result.failure_reason,
                    retry_count=current_retry_count,
                )

        return result

    # Phase B - Batch isolation loop
    def process_batch(
        self,
        document_ids: List[str],
        client_id: str,
        batch_id: Optional[str] = None,
    ) -> BatchResult:
        """
        Process a batch with full per-document isolation.
        GUARANTEE: One document failure NEVER stops the batch.
        Every document processes independently in its own transaction.
        """
        run_id = uuid.uuid4().hex
        batch_id = batch_id or uuid.uuid4().hex[:12]

        batch_logger = logger.bind(
            run_id=run_id,
            batch_id=batch_id,
            client_id=client_id,
            worker_id=self.worker_id,
            processing_stage="entity_matching",
        )

        batch_result = BatchResult(
            run_id=run_id,
            batch_id=batch_id,
            client_id=client_id,
            started_at=datetime.now(timezone.utc),
            total_documents=len(document_ids),
        )

        batch_logger.info("batch_started",
                          total_documents=len(document_ids),
                          max_retries=self.retry_config.max_retries)

        latencies = []

        for idx, document_id in enumerate(document_ids):
            doc_logger = batch_logger.bind(
                document_id=document_id,
                doc_index=idx + 1,
                doc_total=len(document_ids),
            )

            try:
                # Read retry count from DB (separate read-only session)
                retry_db = SessionLocal()
                try:
                    doc = retry_db.query(Document).filter(
                        Document.id == document_id
                    ).first()
                    current_retry_count = (
                        doc.match_retry_count or 0
                    ) if doc else 0
                finally:
                    retry_db.close()

                # CRITICAL: Exception here is caught per-document
                result = self._process_with_retry(
                    document_id=document_id,
                    run_id=run_id,
                    batch_id=batch_id,
                    client_id=client_id,
                    current_retry_count=current_retry_count,
                    doc_logger=doc_logger,
                )

            except Exception as outer_exc:
                # FAILSAFE: Even if _process_with_retry itself fails
                doc_logger.error("batch_document_outer_exception",
                                 document_id=document_id,
                                 exception_type=type(outer_exc).__name__,
                                 error=str(outer_exc),
                                 stack_trace=traceback.format_exc()[:2000])
                result = DocumentResult(
                    document_id=document_id,
                    state=ProcessingState.FAILED,
                    failure_reason=f"outer_exception: {str(outer_exc)[:500]}",
                    exception_type=type(outer_exc).__name__,
                )
                batch_result.db_rollbacks += 1

            # Accumulate stats - batch ALWAYS continues
            batch_result.document_results.append(result)
            latencies.append(result.processing_time_ms)

            if result.state == ProcessingState.MATCHED:
                batch_result.matched += 1
            elif result.state == ProcessingState.FAILED:
                batch_result.failed += 1
            elif result.state == ProcessingState.SKIPPED:
                batch_result.skipped += 1
            elif result.state == ProcessingState.AMBIGUOUS:
                batch_result.ambiguous += 1
            if result.retry_count > 0:
                batch_result.retried += result.retry_count

            # Progress logging every 25 documents
            if (idx + 1) % 25 == 0 or (idx + 1) == len(document_ids):
                batch_logger.info("batch_progress",
                                  processed=idx + 1,
                                  matched=batch_result.matched,
                                  failed=batch_result.failed,
                                  skipped=batch_result.skipped,
                                  ambiguous=batch_result.ambiguous)

        batch_result.completed_at = datetime.now(timezone.utc)
        if latencies:
            batch_result.avg_latency_ms = sum(latencies) / len(latencies)
            batch_result.max_latency_ms = max(latencies)

        batch_logger.info("batch_completed", **batch_result.summary())
        return batch_result

    def process_client(
        self,
        client_id: str,
        batch_id: Optional[str] = None,
        include_already_matched: bool = False,
        limit: int = 500,
    ) -> BatchResult:
        """
        Load all processable documents for a client and run hardened batch.
        W4 fix: Resets stuck PROCESSING documents to PENDING first.
        """
        db = SessionLocal()
        try:
            # W4: Recover documents stuck in PROCESSING
            stuck_docs = db.query(Document).filter(
                Document.processing_status == ProcessingState.PROCESSING
            ).all()
            if stuck_docs:
                for sd in stuck_docs:
                    sd.processing_status = ProcessingState.PENDING
                    sd.match_failure_reason = "recovered_from_stuck_processing"
                db.commit()
                logger.bind(
                    client_id=client_id, worker_id=self.worker_id,
                    processing_stage="entity_matching"
                ).warning("stuck_processing_documents_recovered",
                          count=len(stuck_docs))

            if include_already_matched:
                from app.models.entity import Entity
                entity_ids = db.query(Entity.id).filter(
                    Entity.client_id == client_id
                ).scalar_subquery()
                docs = db.query(Document).join(
                    DocumentMatch, DocumentMatch.document_id == Document.id
                ).filter(
                    DocumentMatch.matched_entity_id.in_(entity_ids)
                ).distinct().limit(limit).all()
            else:
                docs = DocumentStateMachine.get_documents_for_client(
                    db, client_id, limit
                )

            document_ids = [str(d.id) for d in docs]
        finally:
            db.close()

        if not document_ids:
            batch_logger = logger.bind(
                client_id=client_id, worker_id=self.worker_id,
                processing_stage="entity_matching"
            )
            batch_logger.info("client_no_resumable_documents",
                              client_id=client_id)
            return BatchResult(
                run_id=uuid.uuid4().hex,
                batch_id=batch_id or uuid.uuid4().hex[:12],
                client_id=client_id,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )

        return self.process_batch(document_ids, client_id, batch_id)
