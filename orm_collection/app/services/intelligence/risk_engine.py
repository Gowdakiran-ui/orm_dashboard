import datetime
import time
import uuid
import os
import traceback
import structlog
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from app.models.document import Document, DocumentMatch
from app.models.entity import EntityMention, Entity
from app.models.topic import Topic, DocumentTopic
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.trends import TrendEvent
from app.models.risk import RiskEvent
from app.models.risk_state import RiskClientState
from app.models.source import Source, SourceCategory
from app.core.risk_config import (
    TOPIC_WEIGHTS,
    SENTIMENT_WEIGHTS,
    TREND_WEIGHTS,
    DYNAMIC_SOURCE_RELIABILITY_MAP,
    RISK_THRESHOLDS,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Valid state transitions (enforced in _transition_state)
# ---------------------------------------------------------------------------
VALID_TRANSITIONS = {
    "RISK_PENDING":    {"RISK_PROCESSING"},
    "RISK_PROCESSING": {"RISK_COMPLETE", "RISK_FAILED", "RISK_RETRYING", "RISK_SKIPPED"},
    "RISK_COMPLETE":   {"RISK_PROCESSING"},
    "RISK_FAILED":     {"RISK_RETRYING", "RISK_PROCESSING"},
    "RISK_RETRYING":   {"RISK_PROCESSING"},
    "RISK_SKIPPED":    {"RISK_PROCESSING"},
}


def _is_transient_error(exc: Exception) -> bool:
    """Identify transient database or network errors suitable for retry."""
    msg = str(exc).lower()
    transient_indicators = [
        "timeout", "lock", "deadlock", "connection", "read-only",
        "serialization", "temporarily", "operationalerror", "connection refused"
    ]
    return any(indicator in msg for indicator in transient_indicators)


class RiskEngine:
    def __init__(self, *args, **kwargs):
        pass

    # ------------------------------------------------------------------
    # R2 — State Machine Helpers
    # ------------------------------------------------------------------
    def _get_or_create_state(self, db: Session, client_id: str) -> RiskClientState:
        """Retrieve or initialize a RiskClientState row for this client."""
        state = db.query(RiskClientState).filter(
            RiskClientState.client_id == client_id
        ).first()
        if not state:
            state = RiskClientState(
                client_id=client_id,
                processing_status="RISK_PENDING",
                retry_count=0
            )
            db.add(state)
            db.flush()
        return state

    def _transition_state(
        self,
        db: Session,
        state: RiskClientState,
        new_status: str,
        run_id: str = None,
        batch_id: str = None,
        error: str = None,
        log=None
    ):
        """Apply a validated state transition with logger audit."""
        current = state.processing_status
        allowed = VALID_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            if log:
                log.warning(
                    "risk_invalid_state_transition",
                    from_state=current,
                    to_state=new_status,
                    allowed=list(allowed)
                )
        state.processing_status = new_status
        if run_id:
            state.run_id = run_id
        if batch_id:
            state.batch_id = batch_id
        if error is not None:
            state.last_error = str(error)[:1024]
        db.flush()

    # ------------------------------------------------------------------
    # R6 — Duplicate Protection (application-level upsert)
    # ------------------------------------------------------------------
    def _upsert_risk_event(self, db: Session, **kwargs) -> bool:
        """
        Idempotent write for RiskEvent.
        Checks for an existing row with matching:
            (client_id, document_id, entity_id)

        If found: updates risk_score, risk_level, confidence_score,
                  risk_factors, and all observability metadata.
        If not found: inserts a new row.

        Returns True if a new row was created, False if an existing row was updated.
        """
        client_id = kwargs["client_id"]
        document_id = kwargs.get("document_id")
        entity_id = kwargs.get("entity_id")

        query = db.query(RiskEvent).filter(RiskEvent.client_id == client_id)
        if document_id is not None:
            query = query.filter(RiskEvent.document_id == document_id)
        else:
            query = query.filter(RiskEvent.document_id == None)  # noqa: E711

        if entity_id is not None:
            query = query.filter(RiskEvent.entity_id == entity_id)
        else:
            query = query.filter(RiskEvent.entity_id == None)  # noqa: E711

        existing = query.first()
        if existing:
            existing.risk_score = kwargs["risk_score"]
            existing.risk_level = kwargs["risk_level"]
            existing.confidence_score = kwargs["confidence_score"]
            existing.risk_factors = kwargs["risk_factors"]
            existing.run_id = kwargs.get("run_id")
            existing.batch_id = kwargs.get("batch_id")
            existing.worker_id = kwargs.get("worker_id")
            existing.latency_ms = kwargs.get("latency_ms")
            existing.retry_count = kwargs.get("retry_count", 0)
            existing.source_reliability = kwargs.get("source_reliability")
            existing.explainability = kwargs.get("explainability")
            return False  # updated existing

        event = RiskEvent(**kwargs)
        db.add(event)
        return True  # new insert

    # ------------------------------------------------------------------
    # R1 — Atomic Batch Transactions (One transaction per client batch)
    # ------------------------------------------------------------------
    def process_client(
        self,
        db: Session,
        client_id: str,
        run_id: str = None,
        batch_id: str = None,
        attempt: int = 1
    ):
        """
        Execute full risk calculation for all documents of a single client.

        Transaction model (R1):
            - One transaction per client batch.
            - All RiskEvents for a client commit together.
            - Any failure rolls back ONLY that client's batch.
            - No partial batch commits.

        Document Isolation (R5):
            - If a single document fails (malformed data/exception), we rollback ONLY
              that document's changes using a SAVEPOINT, and continue processing
              the remaining documents for the client.
        """
        run_id = run_id or uuid.uuid4().hex
        batch_id = batch_id or uuid.uuid4().hex[:12]
        worker_id = str(os.getpid())
        t_batch_start = time.perf_counter()

        log = logger.bind(
            run_id=run_id,
            batch_id=batch_id,
            client_id=str(client_id),
            worker_id=worker_id,
            task="process_client_risk"
        )

        # --- Transition: → RISK_PROCESSING ---
        state = self._get_or_create_state(db, client_id)
        self._transition_state(db, state, "RISK_PROCESSING", run_id, batch_id, log=log)
        db.commit()  # commit state change in its own atomic block

        log.info("risk_client_started", processing_state="RISK_PROCESSING")

        # Query all documents matched to this client's entities
        doc_ids = db.query(DocumentMatch.document_id).join(
            EntityMention, EntityMention.document_id == DocumentMatch.document_id
        ).filter(EntityMention.entity.has(client_id=client_id)).distinct().all()

        if not doc_ids:
            # Transition: → RISK_SKIPPED
            state = self._get_or_create_state(db, client_id)
            self._transition_state(db, state, "RISK_SKIPPED", run_id, batch_id, log=log)
            db.commit()
            log.info(
                "risk_client_skipped",
                processing_state="RISK_SKIPPED",
                reason="no_documents"
            )
            return

        success_docs = 0
        failed_docs = 0
        all_payloads = []

        try:
            # Loop over all documents using savepoints (R5 Document Isolation)
            for doc_id_tuple in doc_ids:
                doc_id = str(doc_id_tuple[0])
                sp = db.begin_nested()  # SAVEPOINT
                try:
                    payloads = self.calculate_document_risk(
                        db, doc_id, run_id=run_id, batch_id=batch_id,
                        worker_id=worker_id, attempt=attempt, persist=False
                    )
                    if payloads:
                        all_payloads.extend(payloads)
                    success_docs += 1
                    sp.commit()  # Release this document's SAVEPOINT — without this,
                    # each successful document leaves its nested transaction open,
                    # stacking on the next db.begin_nested() call. With enough
                    # documents, the final db.commit() below has to walk back up
                    # through every unreleased savepoint (SQLAlchemy's
                    # self._parent.commit(_to_root=True) chain), deep enough to
                    # hit Python's recursion limit — confirmed live, see FINDINGS.md.
                except Exception as doc_exc:
                    sp.rollback()  # Rollback ONLY this document's savepoint
                    failed_docs += 1
                    log.error(
                        "risk_document_failed",
                        document_id=doc_id,
                        error=str(doc_exc),
                        traceback=traceback.format_exc(),
                        reason="document_processing_error"
                    )
                    # Do NOT propagate the exception. Continue processing remaining documents (R5).

            # Collapse duplicate risk events using a normalized event signature
            collapsed_payloads = {}
            for payload in all_payloads:
                doc = db.query(Document).filter(Document.id == payload["document_id"]).first()
                normalized_title = "".join(c for c in (doc.title or "").lower() if c.isalnum()) if doc else ""
                content_hash = doc.content_hash if doc else ""
                normalized_title_or_hash = content_hash or normalized_title
                
                # Extract main topic name from risk_factors
                topic_name = "unknown"
                for factor in payload.get("risk_factors", []):
                    if factor.get("type") == "Topic":
                        topic_name = factor.get("factor")
                        break
                        
                signature = (payload["client_id"], payload["entity_id"], topic_name, normalized_title_or_hash)
                
                if signature not in collapsed_payloads:
                    collapsed_payloads[signature] = payload
                else:
                    # Retain the strongest evidence (highest risk score)
                    if payload["risk_score"] > collapsed_payloads[signature]["risk_score"]:
                        collapsed_payloads[signature] = payload

            # Persist winning collapsed payloads
            for payload in collapsed_payloads.values():
                is_new = self._upsert_risk_event(db, **payload)
                log.info(
                    "risk_event_committed",
                    client_id=str(payload["client_id"]),
                    document_id=str(payload["document_id"]),
                    entity_id=str(payload["entity_id"]),
                    risk_score=round(payload["risk_score"], 2),
                    risk_level=payload["risk_level"],
                    processing_state="RISK_COMPLETE" if is_new else "RISK_UPDATED"
                )

            # Commit the entire successful batch together (R1 Atomic Transactions)
            db.commit()

            # Transition: → RISK_COMPLETE
            state = self._get_or_create_state(db, client_id)
            self._transition_state(db, state, "RISK_COMPLETE", run_id, batch_id, log=log)
            state.last_run_at = datetime.datetime.now(datetime.timezone.utc)
            state.last_success_at = datetime.datetime.now(datetime.timezone.utc)
            state.retry_count = 0
            state.last_error = None
            db.commit()

            latency_ms = (time.perf_counter() - t_batch_start) * 1000
            log.info(
                "risk_client_completed",
                processing_state="RISK_COMPLETE",
                success_documents=success_docs,
                failed_documents=failed_docs,
                latency_ms=round(latency_ms, 2)
            )

        except Exception as batch_exc:
            db.rollback()  # Hard rollback on the entire client batch transaction

            # Transition: → RISK_FAILED / RISK_RETRYING
            try:
                state = self._get_or_create_state(db, client_id)
                is_transient = _is_transient_error(batch_exc)
                if is_transient and attempt < 3:
                    self._transition_state(db, state, "RISK_RETRYING", run_id, batch_id, error=str(batch_exc), log=log)
                    state.retry_count = attempt
                    state.last_retry_at = datetime.datetime.now(datetime.timezone.utc)
                else:
                    self._transition_state(db, state, "RISK_FAILED", run_id, batch_id, error=str(batch_exc), log=log)
                    state.retry_count = attempt
                state.last_run_at = datetime.datetime.now(datetime.timezone.utc)
                db.commit()
            except Exception as state_exc:
                db.rollback()
                log.error("risk_state_update_failed", error=str(state_exc))

            latency_ms = (time.perf_counter() - t_batch_start) * 1000
            log.error(
                "risk_client_failed",
                processing_state="RISK_FAILED",
                error=str(batch_exc),
                latency_ms=round(latency_ms, 2),
                retry_count=attempt
            )
            raise batch_exc

    def get_risk_level(self, score: float) -> str:
        if score <= RISK_THRESHOLDS["LOW_TO_MEDIUM"]:
            return "LOW"
        elif score <= RISK_THRESHOLDS["MEDIUM_TO_HIGH"]:
            return "MEDIUM"
        elif score <= RISK_THRESHOLDS["HIGH_TO_CRITICAL"]:
            return "HIGH"
        else:
            return "CRITICAL"

    # ------------------------------------------------------------------
    # calculate_document_risk — mathematical calculations unchanged
    # ------------------------------------------------------------------
    def calculate_document_risk(
        self,
        db: Session,
        document_id: str,
        run_id: str = None,
        batch_id: str = None,
        worker_id: str = None,
        attempt: int = 1,
        persist: bool = True
    ):
        """
        Calculate risk for a single document.
        Observability metadata (R8) and Structured Logging (R7) injected.
        """
        t0 = time.perf_counter()
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning("risk_document_not_found", document_id=document_id)
            return []

        # Optimization: Joinedload to avoid N+1 queries when accessing m.entity inside client grouping
        mentions = db.query(EntityMention).options(
            joinedload(EntityMention.entity)
        ).filter(EntityMention.document_id == document_id).all()

        # Group entities by client to generate risk events per client for this document
        client_to_entities = {}
        for m in mentions:
            if m.entity.client_id not in client_to_entities:
                client_to_entities[m.entity.client_id] = []
            client_to_entities[m.entity.client_id].append(m.entity)

        # Optimization: Combined query with outerjoin to fetch Source and SourceCategory in 1 step
        source_reliability = 1.0
        if document.source_id:
            source_info = db.query(Source.name, Source.url, Source.source_type, SourceCategory.name.label("category_name")).outerjoin(
                SourceCategory, Source.category_id == SourceCategory.id
            ).filter(Source.id == document.source_id).first()
            if source_info:
                cat_key = (source_info.category_name or "").lower()
                name_lower = (source_info.name or "").lower()
                url_lower = (source_info.url or "").lower()
                type_lower = (source_info.source_type or "").lower()
                
                matched_key = None
                for key in DYNAMIC_SOURCE_RELIABILITY_MAP.keys():
                    if key != "default":
                        if key in cat_key or key in name_lower or key in url_lower or key in type_lower:
                            matched_key = key
                            break
                
                if matched_key:
                    source_reliability = DYNAMIC_SOURCE_RELIABILITY_MAP[matched_key]
                else:
                    source_reliability = DYNAMIC_SOURCE_RELIABILITY_MAP.get("default", 1.0)

        # Optimization: Eager load Topic relation on DocumentTopic
        doc_topics = db.query(DocumentTopic).options(
            joinedload(DocumentTopic.topic)
        ).filter(DocumentTopic.document_id == document_id).all()
        top_topic = None
        topic_weight = 0
        topic_conf = 1.0

        # Take the highest weighted topic
        for dt in doc_topics:
            if dt.confidence_score >= 0.65:  # Confidence gate to filter noise matches
                t_weight = TOPIC_WEIGHTS.get(dt.topic.name, 0)
                if t_weight > topic_weight:
                    topic_weight = t_weight
                    top_topic = dt.topic.name
                    topic_conf = dt.confidence_score

        # Get Document Sentiment
        doc_sentiments = db.query(DocumentSentiment).filter(DocumentSentiment.document_id == document_id).all()
        sentiment_weight = 0
        sentiment_conf = 1.0
        sent_label = "Neutral"
        if doc_sentiments:
            ds = doc_sentiments[0]
            sent_label = ds.sentiment_label
            sentiment_weight = SENTIMENT_WEIGHTS.get(ds.sentiment_label, 10)
            sentiment_conf = ds.confidence_score

        # Optimization: Pre-fetch all EntitySentiments for this document to avoid N+1 queries in the loop
        ent_sentiments = db.query(EntitySentiment).filter(EntitySentiment.document_id == document_id).all()
        ent_sent_map = {es.entity_id: es for es in ent_sentiments}

        # Optimization: Pre-fetch all TrendEvents for client batch to avoid N+1 queries in the loop
        client_ids = list(client_to_entities.keys())
        trends_by_client_entity = {}
        if client_ids:
            recent_trends_all = db.query(TrendEvent).filter(
                TrendEvent.client_id.in_(client_ids)
            ).order_by(desc(TrendEvent.created_at)).all()
            
            for t in recent_trends_all:
                key = (t.client_id, t.entity_id)
                if key not in trends_by_client_entity:
                    trends_by_client_entity[key] = []
                if len(trends_by_client_entity[key]) < 5:
                    trends_by_client_entity[key].append(t)
                
                key_generic = (t.client_id, None)
                if key_generic not in trends_by_client_entity:
                    trends_by_client_entity[key_generic] = []
                if len(trends_by_client_entity[key_generic]) < 5:
                    trends_by_client_entity[key_generic].append(t)

        payloads = []

        for client_id, entities in client_to_entities.items():
            for entity in entities:
                # Check for entity-specific sentiment overrides (using pre-fetched map)
                ent_sentiment = ent_sent_map.get(entity.id)

                ent_sent_weight = sentiment_weight
                ent_sent_conf = sentiment_conf
                ent_sent_label = sent_label
                if ent_sentiment:
                    ent_sent_label = ent_sentiment.sentiment_label
                    ent_sent_weight = SENTIMENT_WEIGHTS.get(ent_sentiment.sentiment_label, 10)
                    ent_sent_conf = ent_sentiment.confidence_score

                # Get Trends for this entity/client (most severe recent trend from pre-fetched map)
                recent_trends = (
                    trends_by_client_entity.get((client_id, entity.id), []) +
                    trends_by_client_entity.get((client_id, None), [])
                )
                seen_trend_ids = set()
                unique_recent_trends = []
                for t in sorted(recent_trends, key=lambda x: x.created_at, reverse=True):
                    if t.id not in seen_trend_ids:
                        seen_trend_ids.add(t.id)
                        unique_recent_trends.append(t)
                        if len(unique_recent_trends) == 5:
                            break

                trend_weight = 0
                trend_severity = "NONE"
                for t in unique_recent_trends:
                    tw = TREND_WEIGHTS.get(t.severity, 0)
                    if tw > trend_weight:
                        trend_weight = tw
                        trend_severity = t.severity
                # Combine confidence
                confidence_modifier = (topic_conf + ent_sent_conf) / 2.0

                # Base Score
                base_sum = topic_weight + ent_sent_weight + trend_weight

                # Normalize sum
                normalized_base = (base_sum / 240.0) * 100.0

                # Apply Modifiers (Confidence no longer alters severity score)
                final_score = normalized_base * source_reliability
                final_score = min(100.0, max(0.0, final_score))

                risk_factors = []
                if top_topic:
                    risk_factors.append({"type": "Topic", "factor": top_topic, "weight": topic_weight})
                risk_factors.append({"type": "Sentiment", "factor": ent_sent_label, "weight": ent_sent_weight})
                if trend_weight > 0:
                    risk_factors.append({"type": "Trend", "factor": trend_severity, "weight": trend_weight})

                latency_ms = (time.perf_counter() - t0) * 1000

                explainability_data = {
                    "engine_version": "5.2",
                    "formula_version": "1.0",
                    "final_equation": "final_score = min(100.0, max(0.0, (topic_weight + sentiment_weight + trend_weight) / 240.0 * 100.0 * source_reliability))",
                    "individual_weights": {
                        "topic_weight": topic_weight,
                        "sentiment_weight": ent_sent_weight,
                        "trend_weight": trend_weight
                    },
                    "topic_contribution": topic_weight,
                    "sentiment_contribution": ent_sent_weight,
                    "trend_contribution": trend_weight,
                    "source_reliability": source_reliability,
                    "confidence": confidence_modifier,
                    "final_score": final_score,
                    "final_severity": self.get_risk_level(final_score),
                    "decision_reason": f"Risk level set to {self.get_risk_level(final_score)} based on topic '{top_topic}' (weight {topic_weight}), sentiment '{ent_sent_label}' (weight {ent_sent_weight}), trend '{trend_severity}' (weight {trend_weight}), and source reliability {source_reliability}.",
                    "triggering_documents": [str(document_id)]
                }

                payload = {
                    "client_id": client_id,
                    "document_id": document_id,
                    "entity_id": entity.id,
                    "risk_score": final_score,
                    "risk_level": self.get_risk_level(final_score),
                    "confidence_score": confidence_modifier,
                    "risk_factors": risk_factors,
                    "run_id": run_id,
                    "batch_id": batch_id,
                    "worker_id": worker_id,
                    "latency_ms": latency_ms,
                    "retry_count": attempt - 1,
                    "source_reliability": source_reliability,
                    "explainability": explainability_data
                }

                if persist:
                    is_new = self._upsert_risk_event(db, **payload)
                    logger.info(
                        "risk_event_computed",
                        run_id=run_id,
                        batch_id=batch_id,
                        worker_id=worker_id,
                        client_id=str(client_id),
                        document_id=str(document_id),
                        entity_id=str(entity.id),
                        risk_score=round(final_score, 2),
                        risk_level=self.get_risk_level(final_score),
                        latency_ms=round(latency_ms, 2),
                        retry_count=attempt - 1,
                        processing_state="RISK_COMPLETE" if is_new else "RISK_UPDATED"
                    )
                else:
                    payloads.append(payload)

        return payloads
