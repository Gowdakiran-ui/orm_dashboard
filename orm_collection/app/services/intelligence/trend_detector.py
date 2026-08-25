"""
TrendDetector — Phase 4.1 Hardened

Changes from Phase 4.0 baseline:
  R2  State machine: TREND_PENDING → TREND_PROCESSING → TREND_COMPLETE/FAILED/RETRYING/SKIPPED
  R5  Duplicate protection: application-level upsert on (client_id, trend_type, entity_id, topic_id, trend_date)
  R6  Transaction safety: each client runs in its own atomic transaction; commit only on full success
  R7  Structured logging: run_id, batch_id, worker_id, entity_id, topic_id, window, baseline,
      current_value, trend_score, latency, retry_count, processing_state logged on every event
  R9  Baseline safety: entities/topics with zero 7-day history AND no prior TrendEvent history
      are skipped on first observation (no false 999% / CRITICAL events)

Trend calculation algorithm is UNCHANGED from Phase 4.0.
Thresholds are UNCHANGED.
Severity logic is UNCHANGED.
"""
import datetime
import time
import uuid
import os
from sqlalchemy.orm import Session
from sqlalchemy import func
import structlog

from app.models.trends import TrendEvent
from app.models.document import Document
from app.models.entity import Entity, EntityMention
from app.models.topic import Topic, DocumentTopic
from app.models.sentiment import DocumentSentiment
from app.models.trend_state import TrendClientState

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Valid state transitions (enforced in _transition_state)
# ---------------------------------------------------------------------------
VALID_TRANSITIONS = {
    "TREND_PENDING":    {"TREND_PROCESSING"},
    "TREND_PROCESSING": {"TREND_COMPLETE", "TREND_FAILED", "TREND_RETRYING", "TREND_SKIPPED"},
    "TREND_COMPLETE":   {"TREND_PROCESSING"},
    "TREND_FAILED":     {"TREND_RETRYING", "TREND_PROCESSING"},
    "TREND_RETRYING":   {"TREND_PROCESSING"},
    "TREND_SKIPPED":    {"TREND_PROCESSING"},
}


class TrendDetector:
    """
    Hardened Trend Detection engine.

    Public entry points:
        detect_trends(db, client_id, run_id, batch_id)
        process_client(db, client_id, run_id, batch_id)

    Internal sub-detectors (algorithm unchanged):
        _detect_mention_trends(...)
        _detect_topic_trends(...)
        _detect_sentiment_trends(...)
    """

    def __init__(self):
        # No config — thresholds are not modified per R requirements
        pass

    # ------------------------------------------------------------------
    # Severity calculation — UNCHANGED from Phase 4.0
    # ------------------------------------------------------------------
    def calculate_severity(self, percentage_change: float) -> str:
        change = abs(percentage_change)
        if change >= 500:
            return "CRITICAL"
        elif change >= 200:
            return "HIGH"
        elif change >= 50:
            return "MEDIUM"
        else:
            return "LOW"

    # ------------------------------------------------------------------
    # R2 — State Machine
    # ------------------------------------------------------------------
    def _get_or_create_state(self, db: Session, client_id: str) -> TrendClientState:
        """Retrieve or initialize a TrendClientState row for this client."""
        state = db.query(TrendClientState).filter(
            TrendClientState.client_id == client_id
        ).first()
        if not state:
            state = TrendClientState(
                client_id=client_id,
                processing_status="TREND_PENDING",
                retry_count=0
            )
            db.add(state)
            db.flush()
        return state

    def _transition_state(
        self,
        db: Session,
        state: TrendClientState,
        new_status: str,
        run_id: str = None,
        batch_id: str = None,
        error: str = None,
        log=None
    ):
        """
        Apply a validated state transition.
        Logs invalid transitions as warnings but does NOT raise — observability over hard failure.
        """
        current = state.processing_status
        allowed = VALID_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            if log:
                log.warning(
                    "trend_invalid_state_transition",
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
    # R9 — Baseline Safety
    # ------------------------------------------------------------------
    def _has_prior_trend_history(
        self,
        db: Session,
        client_id: str,
        trend_type: str,
        entity_id=None,
        topic_id=None
    ) -> bool:
        """
        Returns True if at least one TrendEvent has been stored for this
        (client, type, entity/topic) combination on a PREVIOUS calendar day.

        This is used to distinguish a genuine first observation (no baseline
        established) from a zero-baseline condition on an entity with history
        that happens to have no documents in the 7-day window.
        """
        now_override_env = os.environ.get("TREND_DETECTOR_NOW_OVERRIDE")
        if now_override_env:
            try:
                today = datetime.datetime.fromisoformat(now_override_env).date()
            except ValueError:
                today = datetime.date.fromisoformat(now_override_env)
        else:
            today = datetime.date.today()

        query = db.query(TrendEvent).filter(
            TrendEvent.client_id == client_id,
            TrendEvent.trend_type == trend_type,
            TrendEvent.trend_date < today
        )
        if entity_id is not None:
            query = query.filter(TrendEvent.entity_id == entity_id)
        if topic_id is not None:
            query = query.filter(TrendEvent.topic_id == topic_id)
        return query.first() is not None

    # ------------------------------------------------------------------
    # R5 — Duplicate Protection (application-level upsert)
    # ------------------------------------------------------------------
    def _upsert_trend_event(self, db: Session, **kwargs) -> bool:
        """
        Idempotent write for TrendEvent.

        Checks for an existing row with matching:
            (client_id, trend_type, entity_id, topic_id, trend_date)

        If found: updates baseline_value, current_value, percentage_change,
                  severity, run_id, batch_id, explainability fields.
        If not found: inserts a new row.

        Returns True if a new row was created, False if an existing row was updated.
        """
        trend_date = kwargs.get("trend_date")
        client_id = kwargs["client_id"]
        trend_type = kwargs["trend_type"]
        entity_id = kwargs.get("entity_id")
        topic_id = kwargs.get("topic_id")

        query = db.query(TrendEvent).filter(
            TrendEvent.client_id == client_id,
            TrendEvent.trend_type == trend_type,
            TrendEvent.trend_date == trend_date
        )
        # Exact NULL matching — must use `== None` (SQLAlchemy idiom for IS NULL)
        if entity_id is not None:
            query = query.filter(TrendEvent.entity_id == entity_id)
        else:
            query = query.filter(TrendEvent.entity_id == None)  # noqa: E711
        if topic_id is not None:
            query = query.filter(TrendEvent.topic_id == topic_id)
        else:
            query = query.filter(TrendEvent.topic_id == None)  # noqa: E711

        existing = query.first()
        if existing:
            existing.baseline_value = kwargs["baseline_value"]
            existing.current_value = kwargs["current_value"]
            existing.percentage_change = kwargs["percentage_change"]
            existing.severity = kwargs["severity"]
            existing.run_id = kwargs.get("run_id")
            existing.batch_id = kwargs.get("batch_id")
            existing.baseline_established = kwargs.get("baseline_established", True)
            existing.trend_direction = kwargs.get("trend_direction")
            existing.decision_reason = kwargs.get("decision_reason")
            existing.triggering_documents = kwargs.get("triggering_documents")
            existing.time_window = kwargs.get("time_window", "24h_vs_7d")
            return False  # updated existing

        event = TrendEvent(**kwargs)
        db.add(event)
        return True  # new insert

    # ------------------------------------------------------------------
    # R2+R6+R7 — Main entry point with state machine and structured logging
    # ------------------------------------------------------------------
    def detect_trends(
        self,
        db: Session,
        client_id: str,
        run_id: str = None,
        batch_id: str = None
    ):
        """
        Execute full trend detection for a single client.

        Transaction model:
            - All three sub-detectors run inside a single transaction.
            - db.commit() is called once on success.
            - On any exception: db.rollback() → state → TREND_FAILED.
            - The state transition commit is a SEPARATE, minimal session operation
               so state updates survive the main transaction rollback.

        R6 guarantee: rolling back this client never affects other clients.
        """
        run_id = run_id or uuid.uuid4().hex
        batch_id = batch_id or uuid.uuid4().hex[:12]
        worker_id = os.getpid()
        now_override_env = os.environ.get("TREND_DETECTOR_NOW_OVERRIDE")
        if now_override_env:
            try:
                now = datetime.datetime.fromisoformat(now_override_env)
            except ValueError:
                now = datetime.datetime.combine(datetime.date.fromisoformat(now_override_env), datetime.time.min).replace(tzinfo=datetime.timezone.utc)
            trend_date = now.date()
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
            trend_date = datetime.date.today()

        last_24h = now - datetime.timedelta(days=1)
        prev_7d_start = last_24h - datetime.timedelta(days=7)

        # Bind structured log context for this entire client execution
        log = logger.bind(
            run_id=run_id,
            batch_id=batch_id,
            client_id=str(client_id),
            worker_id=worker_id,
            trend_window="24h_vs_7d",
            trend_date=str(trend_date)
        )

        # --- Early return: fetch entities before touching the state table ---
        # Guards against non-existent client_ids causing FK violations in trend_client_states.
        entities = db.query(Entity).filter(Entity.client_id == client_id).all()
        if not entities:
            log.info(
                "trend_detection_skipped",
                processing_state="TREND_SKIPPED",
                reason="no_entities"
            )
            return

        # --- Transition: → TREND_PROCESSING ---
        state = self._get_or_create_state(db, client_id)
        retry_count = state.retry_count or 0
        self._transition_state(db, state, "TREND_PROCESSING", run_id, batch_id, log=log)
        db.flush()

        log.info(
            "trend_detection_started",
            processing_state="TREND_PROCESSING",
            retry_count=retry_count
        )
        t_start = time.perf_counter()

        try:
            # ==========================================================
            # A2 — Dynamic Baseline: Calculate System Ingestion Days
            # ==========================================================
            # Counts the number of days in the 7-day window that actually had any documents ingested.
            # This ignores days with zero collection/failures so they don't drag down the baseline.
            system_active_days = db.query(func.count(func.distinct(func.date(Document.collected_at)))).filter(
                Document.collected_at >= prev_7d_start,
                Document.collected_at < last_24h
            ).scalar() or 0

            # Fallback/safety: if active days is less than 2, we have sparse/incomplete data.
            # To prevent unstable baselines, we set baseline_established = False (cold start) or fallback to 7.
            divisor = float(system_active_days) if system_active_days >= 2 else 7.0
            baseline_established = (system_active_days >= 2)

            log.info(
                "trend_baseline_divisor_calculated",
                system_active_days=system_active_days,
                divisor=divisor,
                baseline_established=baseline_established
            )

            mention_events = self._detect_mention_trends(
                db, client_id, entities, now, last_24h, prev_7d_start,
                run_id, batch_id, worker_id, trend_date, log, divisor, system_active_days, baseline_established
            )
            topic_events = self._detect_topic_trends(
                db, client_id, now, last_24h, prev_7d_start,
                run_id, batch_id, worker_id, trend_date, log, divisor, system_active_days, baseline_established
            )
            sentiment_events = self._detect_sentiment_trends(
                db, client_id, now, last_24h, prev_7d_start,
                run_id, batch_id, worker_id, trend_date, log, divisor, system_active_days, baseline_established
            )

            # --- Single commit for all three detectors ---
            db.commit()

            latency_ms = (time.perf_counter() - t_start) * 1000

            # Update state to COMPLETE (separate commit after detection commit)
            state = self._get_or_create_state(db, client_id)
            self._transition_state(db, state, "TREND_COMPLETE", run_id, batch_id, log=log)
            state.last_run_at = now
            state.last_success_at = now
            state.retry_count = 0
            state.last_error = None
            db.commit()

            log.info(
                "trend_detection_complete",
                processing_state="TREND_COMPLETE",
                mention_events=mention_events,
                topic_events=topic_events,
                sentiment_events=sentiment_events,
                total_events=mention_events + topic_events + sentiment_events,
                latency_ms=round(latency_ms, 2)
            )

        except Exception as exc:
            db.rollback()
            latency_ms = (time.perf_counter() - t_start) * 1000

            # Update state in a fresh flush after rollback
            try:
                state = self._get_or_create_state(db, client_id)
                state.retry_count = (state.retry_count or 0) + 1
                self._transition_state(
                    db, state, "TREND_FAILED",
                    run_id, batch_id,
                    error=str(exc),
                    log=log
                )
                state.last_run_at = now
                db.commit()
            except Exception as state_exc:
                db.rollback()
                log.error(
                    "trend_state_update_failed",
                    state_error=str(state_exc)
                )

            log.error(
                "trend_detection_failed",
                processing_state="TREND_FAILED",
                error=str(exc),
                latency_ms=round(latency_ms, 2),
                retry_count=retry_count,
                exc_info=True
            )
            raise  # re-raise so caller (aggregation_tasks) can handle per-client

    # ------------------------------------------------------------------
    # Sub-detector: Mention Trends (algorithm unchanged from Phase 4.0)
    # ------------------------------------------------------------------
    def _detect_mention_trends(
        self, db, client_id, entities, now, last_24h, prev_7d_start,
        run_id, batch_id, worker_id, trend_date, log, divisor, system_active_days, baseline_established
    ) -> int:
        """
        Detect mention-volume spikes per entity.
        Returns count of TrendEvents created or updated.
        """
        events_count = 0

        for entity in entities:
            t0 = time.perf_counter()

            # --- Baseline: SUM of mention_count over prior 7 days ---
            baseline_count = (
                db.query(func.sum(EntityMention.mention_count))
                .join(Document, Document.id == EntityMention.document_id)
                .filter(EntityMention.entity_id == entity.id)
                .filter(
                    Document.collected_at >= prev_7d_start,
                    Document.collected_at < last_24h
                )
                .scalar() or 0
            )
            baseline_avg = baseline_count / divisor

            # --- Current: SUM of mention_count in last 24 hours ---
            current_count = (
                db.query(func.sum(EntityMention.mention_count))
                .join(Document, Document.id == EntityMention.document_id)
                .filter(EntityMention.entity_id == entity.id)
                .filter(
                    Document.collected_at >= last_24h,
                    Document.collected_at <= now
                )
                .scalar() or 0
            )

            # Nothing to compute
            if current_count == 0 and baseline_avg == 0:
                continue

            # R9 — Baseline Safety: first observation guard
            is_established = baseline_established
            if baseline_avg == 0 and current_count > 0:
                percent_change = 100.0  # Allow first-time spikes to trigger
            else:
                percent_change = ((current_count - baseline_avg) / baseline_avg) * 100.0

            latency_ms = (time.perf_counter() - t0) * 1000

            log.info(
                "trend_mention_computed",
                entity_id=str(entity.id),
                trend_type="Mention",
                baseline=round(baseline_avg, 4),
                current_value=current_count,
                trend_score=round(percent_change, 2),
                latency_ms=round(latency_ms, 2)
            )

            # T11-F1: gate firing on is_established, mirroring the Sentiment
            # trend types below (lines ~703, ~806) which already correctly
            # require this. Without it, an entity's first-ever single
            # mention hardcodes percent_change=100.0 (>=50.0 MEDIUM
            # threshold) and fires a spurious trend spike alert for a
            # newly-tracked entity that has no real baseline yet.
            if abs(percent_change) >= 50.0 and is_established:
                severity = self.calculate_severity(percent_change)

                # Fetch triggering documents in last 24h for explainability
                trigger_docs = (
                    db.query(Document.id)
                    .join(EntityMention, EntityMention.document_id == Document.id)
                    .filter(EntityMention.entity_id == entity.id)
                    .filter(Document.collected_at >= last_24h, Document.collected_at <= now)
                    .limit(3)
                    .all()
                )
                triggering_ids = [str(d[0]) for d in trigger_docs]

                direction = "RISING" if percent_change >= 0 else "FALLING"
                decision = f"Mention volume for entity '{entity.name}' surged to {current_count} in the last 24h compared to a historical baseline of {baseline_avg:.2f} daily mentions ({percent_change:+.1f}% change) over {system_active_days} active collection days."

                is_new = self._upsert_trend_event(
                    db,
                    client_id=client_id,
                    trend_type="Mention",
                    entity_id=entity.id,
                    baseline_value=baseline_avg,
                    current_value=float(current_count),
                    percentage_change=percent_change,
                    severity=severity,
                    run_id=run_id,
                    batch_id=batch_id,
                    trend_date=trend_date,
                    baseline_established=is_established,
                    trend_direction=direction,
                    decision_reason=decision,
                    triggering_documents=triggering_ids,
                    time_window="24h_vs_7d"
                )
                events_count += 1
                log.info(
                    "trend_event_upserted",
                    entity_id=str(entity.id),
                    trend_type="Mention",
                    severity=severity,
                    trend_score=round(percent_change, 2),
                    is_new_insert=is_new
                )

        return events_count

    # ------------------------------------------------------------------
    # Sub-detector: Topic Trends (algorithm unchanged from Phase 4.0)
    # ------------------------------------------------------------------
    def _detect_topic_trends(
        self, db, client_id, now, last_24h, prev_7d_start,
        run_id, batch_id, worker_id, trend_date, log, divisor, system_active_days, baseline_established
    ) -> int:
        """
        Detect topic-volume spikes per active topic (client-aware topic list).
        Returns count of TrendEvents created or updated.
        """
        client_docs_query = (
            db.query(EntityMention.document_id)
            .join(Entity, Entity.id == EntityMention.entity_id)
            .filter(Entity.client_id == client_id)
            .scalar_subquery()
        )

        # A4 Client-Aware Topic Evaluation: only evaluate topics present in the client's documents
        topics = (
            db.query(Topic)
            .join(DocumentTopic, DocumentTopic.topic_id == Topic.id)
            .filter(Topic.is_active == True)
            .filter(DocumentTopic.document_id.in_(client_docs_query))
            .distinct()
            .all()
        )
        events_count = 0

        for topic in topics:
            t0 = time.perf_counter()

            # --- Baseline ---
            baseline_count = (
                db.query(func.count(DocumentTopic.id))
                .join(Document, Document.id == DocumentTopic.document_id)
                .filter(DocumentTopic.topic_id == topic.id)
                .filter(Document.id.in_(client_docs_query))
                .filter(
                    Document.collected_at >= prev_7d_start,
                    Document.collected_at < last_24h
                )
                .scalar() or 0
            )
            baseline_avg = baseline_count / divisor

            # --- Current ---
            current_count = (
                db.query(func.count(DocumentTopic.id))
                .join(Document, Document.id == DocumentTopic.document_id)
                .filter(DocumentTopic.topic_id == topic.id)
                .filter(Document.id.in_(client_docs_query))
                .filter(
                    Document.collected_at >= last_24h,
                    Document.collected_at <= now
                )
                .scalar() or 0
            )

            if current_count == 0 and baseline_avg == 0:
                continue

            # R9 — Baseline Safety
            is_established = baseline_established
            if baseline_avg == 0 and current_count > 0:
                percent_change = 100.0  # Allow first-time spikes to trigger
            else:
                percent_change = ((current_count - baseline_avg) / baseline_avg) * 100.0

            latency_ms = (time.perf_counter() - t0) * 1000

            log.info(
                "trend_topic_computed",
                topic_id=str(topic.id),
                trend_type="Topic",
                baseline=round(baseline_avg, 4),
                current_value=current_count,
                trend_score=round(percent_change, 2),
                latency_ms=round(latency_ms, 2)
            )

            # T11-F1: same is_established gate as the Mention trend type above.
            if abs(percent_change) >= 50.0 and is_established:
                severity = self.calculate_severity(percent_change)

                # Fetch triggering documents
                trigger_docs = (
                    db.query(Document.id)
                    .join(DocumentTopic, DocumentTopic.document_id == Document.id)
                    .filter(DocumentTopic.topic_id == topic.id)
                    .filter(Document.id.in_(client_docs_query))
                    .filter(Document.collected_at >= last_24h, Document.collected_at <= now)
                    .limit(3)
                    .all()
                )
                triggering_ids = [str(d[0]) for d in trigger_docs]

                direction = "RISING" if percent_change >= 0 else "FALLING"
                decision = f"Topic '{topic.name}' volume surged to {current_count} in the last 24h compared to a historical baseline of {baseline_avg:.2f} daily documents ({percent_change:+.1f}% change) over {system_active_days} active collection days."

                is_new = self._upsert_trend_event(
                    db,
                    client_id=client_id,
                    trend_type="Topic",
                    topic_id=topic.id,
                    baseline_value=baseline_avg,
                    current_value=float(current_count),
                    percentage_change=percent_change,
                    severity=severity,
                    run_id=run_id,
                    batch_id=batch_id,
                    trend_date=trend_date,
                    baseline_established=is_established,
                    trend_direction=direction,
                    decision_reason=decision,
                    triggering_documents=triggering_ids,
                    time_window="24h_vs_7d"
                )
                events_count += 1
                log.info(
                    "trend_event_upserted",
                    topic_id=str(topic.id),
                    trend_type="Topic",
                    severity=severity,
                    trend_score=round(percent_change, 2),
                    is_new_insert=is_new
                )

        return events_count

    # ------------------------------------------------------------------
    # Sub-detector: Sentiment Trends (algorithm unchanged from Phase 4.0)
    # ------------------------------------------------------------------
    def _detect_sentiment_trends(
        self, db, client_id, now, last_24h, prev_7d_start,
        run_id, batch_id, worker_id, trend_date, log, divisor, system_active_days, baseline_established
    ) -> int:
        """
        Detect negative and positive sentiment volume spikes at the client level.
        Returns count of TrendEvents created/updated.
        """
        client_docs_query = (
            db.query(EntityMention.document_id)
            .join(Entity, Entity.id == EntityMention.entity_id)
            .filter(Entity.client_id == client_id)
            .scalar_subquery()
        )

        events_count = 0

        # ==========================================
        # 1. Negative Sentiment Spike Detection
        # ==========================================
        t0 = time.perf_counter()

        # --- Baseline ---
        baseline_neg_count = (
            db.query(func.count(DocumentSentiment.id))
            .join(Document, Document.id == DocumentSentiment.document_id)
            .filter(DocumentSentiment.sentiment_label == "Negative")
            .filter(Document.id.in_(client_docs_query))
            .filter(
                Document.collected_at >= prev_7d_start,
                Document.collected_at < last_24h
            )
            .scalar() or 0
        )
        baseline_neg_avg = baseline_neg_count / divisor

        # --- Current ---
        current_neg_count = (
            db.query(func.count(DocumentSentiment.id))
            .join(Document, Document.id == DocumentSentiment.document_id)
            .filter(DocumentSentiment.sentiment_label == "Negative")
            .filter(Document.id.in_(client_docs_query))
            .filter(
                Document.collected_at >= last_24h,
                Document.collected_at <= now
            )
            .scalar() or 0
        )

        if current_neg_count > 0 or baseline_neg_avg > 0:
            is_established = baseline_established
            if baseline_neg_avg == 0 and current_neg_count > 0:
                percent_change_neg = 100.0
            else:
                percent_change_neg = ((current_neg_count - baseline_neg_avg) / baseline_neg_avg) * 100.0

            latency_ms = (time.perf_counter() - t0) * 1000

            log.info(
                "trend_sentiment_computed",
                trend_type="Sentiment",
                sentiment_direction="negative",
                baseline=round(baseline_neg_avg, 4),
                current_value=current_neg_count,
                trend_score=round(percent_change_neg, 2),
                latency_ms=round(latency_ms, 2)
            )

            # Negative sentiment surge triggers alert
            if percent_change_neg >= 50.0 and is_established:
                severity = self.calculate_severity(percent_change_neg)

                # Fetch triggering documents
                trigger_docs = (
                    db.query(Document.id)
                    .join(DocumentSentiment, DocumentSentiment.document_id == Document.id)
                    .filter(DocumentSentiment.sentiment_label == "Negative")
                    .filter(Document.id.in_(client_docs_query))
                    .filter(Document.collected_at >= last_24h, Document.collected_at <= now)
                    .limit(3)
                    .all()
                )
                triggering_ids = [str(d[0]) for d in trigger_docs]

                decision = f"Negative sentiment volume surged to {current_neg_count} in the last 24h compared to a historical baseline of {baseline_neg_avg:.2f} daily negative documents ({percent_change_neg:+.1f}% change) over {system_active_days} active collection days."

                is_new = self._upsert_trend_event(
                    db,
                    client_id=client_id,
                    trend_type="Sentiment",
                    baseline_value=baseline_neg_avg,
                    current_value=float(current_neg_count),
                    percentage_change=percent_change_neg,
                    severity=severity,
                    run_id=run_id,
                    batch_id=batch_id,
                    trend_date=trend_date,
                    baseline_established=True,
                    trend_direction="negative",
                    decision_reason=decision,
                    triggering_documents=triggering_ids,
                    time_window="24h_vs_7d"
                )
                events_count += 1
                log.info(
                    "trend_event_upserted",
                    trend_type="Sentiment",
                    severity=severity,
                    trend_score=round(percent_change_neg, 2),
                    is_new_insert=is_new
                )

        # ==========================================
        # 2. Positive Sentiment Spike Detection (A3)
        # ==========================================
        t0_pos = time.perf_counter()

        # --- Baseline ---
        baseline_pos_count = (
            db.query(func.count(DocumentSentiment.id))
            .join(Document, Document.id == DocumentSentiment.document_id)
            .filter(DocumentSentiment.sentiment_label == "Positive")
            .filter(Document.id.in_(client_docs_query))
            .filter(
                Document.collected_at >= prev_7d_start,
                Document.collected_at < last_24h
            )
            .scalar() or 0
        )
        baseline_pos_avg = baseline_pos_count / divisor

        # --- Current ---
        current_pos_count = (
            db.query(func.count(DocumentSentiment.id))
            .join(Document, Document.id == DocumentSentiment.document_id)
            .filter(DocumentSentiment.sentiment_label == "Positive")
            .filter(Document.id.in_(client_docs_query))
            .filter(
                Document.collected_at >= last_24h,
                Document.collected_at <= now
            )
            .scalar() or 0
        )

        if current_pos_count > 0 or baseline_pos_avg > 0:
            is_established = baseline_established
            if baseline_pos_avg == 0 and current_pos_count > 0:
                if not self._has_prior_trend_history(db, client_id, "Sentiment_Positive"):
                    log.info(
                        "trend_baseline_not_established",
                        trend_type="Sentiment_Positive",
                        action="SKIPPED",
                        reason="first_observation_no_baseline"
                    )
                    is_established = False
                percent_change_pos = 999.0
            else:
                percent_change_pos = ((current_pos_count - baseline_pos_avg) / baseline_pos_avg) * 100.0

            latency_ms_pos = (time.perf_counter() - t0_pos) * 1000

            log.info(
                "trend_sentiment_computed",
                trend_type="Sentiment_Positive",
                sentiment_direction="positive",
                baseline=round(baseline_pos_avg, 4),
                current_value=current_pos_count,
                trend_score=round(percent_change_pos, 2),
                latency_ms=round(latency_ms_pos, 2)
            )

            # Positive sentiment surge triggers alert (A3)
            if percent_change_pos >= 50.0 and is_established:
                severity = self.calculate_severity(percent_change_pos)

                # Fetch triggering documents
                trigger_docs = (
                    db.query(Document.id)
                    .join(DocumentSentiment, DocumentSentiment.document_id == Document.id)
                    .filter(DocumentSentiment.sentiment_label == "Positive")
                    .filter(Document.id.in_(client_docs_query))
                    .filter(Document.collected_at >= last_24h, Document.collected_at <= now)
                    .limit(3)
                    .all()
                )
                triggering_ids = [str(d[0]) for d in trigger_docs]

                decision = f"Positive sentiment volume surged to {current_pos_count} in the last 24h compared to a historical baseline of {baseline_pos_avg:.2f} daily positive documents ({percent_change_pos:+.1f}% change) over {system_active_days} active collection days."

                is_new = self._upsert_trend_event(
                    db,
                    client_id=client_id,
                    trend_type="Sentiment_Positive",
                    baseline_value=baseline_pos_avg,
                    current_value=float(current_pos_count),
                    percentage_change=percent_change_pos,
                    severity=severity,
                    run_id=run_id,
                    batch_id=batch_id,
                    trend_date=trend_date,
                    baseline_established=True,
                    trend_direction="positive",
                    decision_reason=decision,
                    triggering_documents=triggering_ids,
                    time_window="24h_vs_7d"
                )
                events_count += 1
                log.info(
                    "trend_event_upserted",
                    trend_type="Sentiment_Positive",
                    severity=severity,
                    trend_score=round(percent_change_pos, 2),
                    is_new_insert=is_new
                )

        return events_count

    # ------------------------------------------------------------------
    # Compatibility entry point (used by aggregation_tasks)
    # ------------------------------------------------------------------
    def process_client(
        self,
        db: Session,
        client_id: str,
        run_id: str = None,
        batch_id: str = None
    ):
        self.detect_trends(db, client_id, run_id=run_id, batch_id=batch_id)

