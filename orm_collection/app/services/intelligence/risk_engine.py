import datetime
import time
import uuid
import os
import traceback
import structlog
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, text

from app.models.document import Document, DocumentMatch
from app.models.entity import EntityMention, Entity
from app.models.topic import Topic, DocumentTopic
from app.models.sentiment import DocumentSentiment, EntitySentiment
from app.models.trends import TrendEvent
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
    def _upsert_risk_event(self, db: Session, **kwargs) -> str:
        """
        Concurrency-safe upsert for RiskEvent, matched against the
        existing uq_risk_events_daily unique index on
        (client_id, document_id, entity_id).

        A single atomic INSERT ... ON CONFLICT ... DO UPDATE ... WHERE
        statement enforces a standing invariant: an incoming write may
        only replace an existing row if its
        explainability.role_classification_source is a strictly higher
        quality tier ("llm" beats "fallback_unchanged"/"not_evaluated"/
        missing), or -- within the same tier -- if it was computed more
        recently (computed_at). A lower-quality or stale-same-quality
        write is rejected by Postgres itself (the WHERE clause is false,
        so DO UPDATE touches nothing and RETURNING yields no row) rather
        than silently clobbering a better result.

        Confirmed live: the hourly celery-beat calculate_client_risks
        full-corpus scan and an on-demand pipeline run can both score
        the same (client, document, entity) concurrently, and the prior
        plain SELECT-then-branch UPDATE/INSERT let whichever transaction
        committed LAST win even off a stale read -- a worse
        (fallback_unchanged) result overwriting a better (llm) one
        computed moments earlier. A two-step app-level compare-then-write
        cannot close that gap no matter how careful the comparison is,
        because the race is between the read and the write, not in the
        comparison logic. A single ON CONFLICT ... DO UPDATE ... WHERE
        statement closes it with no extra locking needed: Postgres takes
        the conflicting row's lock as an intrinsic part of resolving the
        conflict, so two concurrent writers to the same key serialize
        automatically and each WHERE predicate is evaluated against the
        truly-current committed state, not a stale pre-transaction read.

        Returns "inserted", "updated", or "skipped" (a lower-quality or
        stale write was correctly rejected -- log this for visibility,
        never treat it as silently dropped).
        """
        import json as _json

        client_id = kwargs["client_id"]
        document_id = kwargs.get("document_id")
        entity_id = kwargs.get("entity_id")
        explainability = kwargs.get("explainability")
        risk_factors = kwargs.get("risk_factors")
        computed_at = kwargs.get("computed_at") or datetime.datetime.now(datetime.timezone.utc)
        new_id = uuid.uuid4()

        result = db.execute(
            text("""
                INSERT INTO risk_events (
                    id, client_id, document_id, entity_id, risk_score, risk_level,
                    confidence_score, risk_factors, run_id, batch_id, worker_id,
                    latency_ms, retry_count, source_reliability, explainability,
                    computed_at
                ) VALUES (
                    :id, :client_id, :document_id, :entity_id, :risk_score, :risk_level,
                    :confidence_score, :risk_factors, :run_id, :batch_id, :worker_id,
                    :latency_ms, :retry_count, :source_reliability,
                    CAST(:explainability AS json), :computed_at
                )
                ON CONFLICT (client_id, COALESCE(document_id::text, ''), COALESCE(entity_id::text, ''))
                DO UPDATE SET
                    risk_score = EXCLUDED.risk_score,
                    risk_level = EXCLUDED.risk_level,
                    confidence_score = EXCLUDED.confidence_score,
                    risk_factors = EXCLUDED.risk_factors,
                    run_id = EXCLUDED.run_id,
                    batch_id = EXCLUDED.batch_id,
                    worker_id = EXCLUDED.worker_id,
                    latency_ms = EXCLUDED.latency_ms,
                    retry_count = EXCLUDED.retry_count,
                    source_reliability = EXCLUDED.source_reliability,
                    explainability = EXCLUDED.explainability,
                    computed_at = EXCLUDED.computed_at
                WHERE
                    (COALESCE(EXCLUDED.explainability->>'role_classification_source', '') = 'llm')::int
                    > (COALESCE(risk_events.explainability->>'role_classification_source', '') = 'llm')::int
                    OR (
                        (COALESCE(EXCLUDED.explainability->>'role_classification_source', '') = 'llm')
                        = (COALESCE(risk_events.explainability->>'role_classification_source', '') = 'llm')
                        AND EXCLUDED.computed_at >= COALESCE(risk_events.computed_at, '-infinity'::timestamptz)
                    )
                RETURNING id
            """),
            {
                "id": new_id,
                "client_id": client_id,
                "document_id": document_id,
                "entity_id": entity_id,
                "risk_score": kwargs["risk_score"],
                "risk_level": kwargs["risk_level"],
                "confidence_score": kwargs["confidence_score"],
                "risk_factors": _json.dumps(risk_factors) if risk_factors is not None else None,
                "run_id": kwargs.get("run_id"),
                "batch_id": kwargs.get("batch_id"),
                "worker_id": kwargs.get("worker_id"),
                "latency_ms": kwargs.get("latency_ms"),
                "retry_count": kwargs.get("retry_count", 0),
                "source_reliability": kwargs.get("source_reliability"),
                "explainability": _json.dumps(explainability) if explainability is not None else None,
                "computed_at": computed_at,
            }
        )
        row = result.first()
        if row is None:
            return "skipped"
        # ON CONFLICT DO UPDATE never touches `id` (not in the SET list),
        # so the existing row keeps its own original id -- comparing
        # against the id we generated for this call is a deterministic
        # way to tell insert from update, no xmax heuristics needed.
        return "inserted" if row.id == new_id else "updated"

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
                write_result = self._upsert_risk_event(db, **payload)
                if write_result == "skipped":
                    log.info(
                        "risk_event_write_skipped_lower_quality",
                        client_id=str(payload["client_id"]),
                        document_id=str(payload["document_id"]),
                        entity_id=str(payload["entity_id"]),
                        incoming_role_source=(payload.get("explainability") or {}).get("role_classification_source"),
                    )
                    continue
                log.info(
                    "risk_event_committed",
                    client_id=str(payload["client_id"]),
                    document_id=str(payload["document_id"]),
                    entity_id=str(payload["entity_id"]),
                    risk_score=round(payload["risk_score"], 2),
                    risk_level=payload["risk_level"],
                    processing_state="RISK_COMPLETE" if write_result == "inserted" else "RISK_UPDATED"
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

    # ------------------------------------------------------------------
    # LLM-assisted SELF/BYSTANDER/EXONERATED role classification
    # ------------------------------------------------------------------
    # Only called for documents whose mechanically-computed final_score
    # already exceeds the LOW/MEDIUM boundary (RISK_THRESHOLDS) -- a
    # document the formula already scores LOW has little at stake either
    # way, and calling out to OpenRouter on every one of the ~2,300+
    # documents in this corpus would risk becoming the next throughput
    # bottleneck in an already latency-sensitive per-document pipeline,
    # for no real benefit. MEDIUM+ is where a false "this is about the
    # client" actually inflates something that matters -- the real
    # CEO-complaint failure mode confirmed live tonight (Godrej/Orris:
    # Godrej is a bystander in Orris's legal matter, not the wrongdoer).
    RISK_ROLE_CLASSIFICATION_MIN_SCORE = 25.0

    def _llm_classify_role(self, document, entity, client_id, run_id=None):
        """
        Classifies whether this document is genuinely negative news ABOUT
        this entity (SELF), the entity merely appears as another party
        (BYSTANDER), or the entity is party to a negative-sounding dispute
        that actually resolved in its favor (EXONERATED).

        Returns "SELF", "BYSTANDER", or "EXONERATED" on a confident,
        well-formed response, or None on ANY failure -- missing API key,
        timeout, network error, non-200, null/malformed content, or a
        label outside the three valid values. None means "no change to
        today's existing scoring" (the caller treats None the same as
        SELF) -- an OpenRouter outage must never silently suppress a
        real risk score, only ever fail back to the status quo.
        """
        import requests
        import json as _json

        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            return None

        log = logger.bind(run_id=run_id, task="risk_llm_role_classify", client_id=str(client_id), entity_id=str(entity.id))

        system_prompt = (
            "You classify a news document's role relative to one specific entity. "
            "Given the entity name and a document title, decide exactly one of:\n"
            "SELF - the document is negative news ABOUT the entity itself (it is the "
            "accused, the defendant, the one taking the negative action, or otherwise "
            "the actual subject of the negative story).\n"
            "BYSTANDER - the entity merely appears as another party (filer, plaintiff, "
            "spokesperson, a person/company mentioned in passing) or is not really the "
            "subject of this document at all.\n"
            "EXONERATED - the entity is a party to a negative-sounding situation (a "
            "lawsuit, an accusation, a dispute, scrutiny) but the actual outcome or "
            "framing is favorable to it (it wins, is cleared, the ruling favors it, it "
            "successfully defends itself, it receives a positive result despite "
            "dispute-shaped language).\n"
            'Respond with strict JSON only: {"label": "SELF"|"BYSTANDER"|"EXONERATED"}'
        )
        content_snippet = (document.normalized_content or document.title or "")[:500]
        user_prompt = f'Entity: {entity.name}\nDocument: "{content_snippet}"'

        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek/deepseek-v4-pro",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 200,
                    "reasoning": {"enabled": False},
                    "response_format": {"type": "json_object"},
                },
                timeout=8.0,
            )
            if resp.status_code != 200:
                log.warning("risk_llm_role_http_error", status=resp.status_code, body=resp.text[:300])
                return None

            content = resp.json()["choices"][0]["message"]["content"]
            if content is None:
                log.warning("risk_llm_role_null_content")
                return None

            label = _json.loads(content).get("label", "")
            if not isinstance(label, str):
                log.warning("risk_llm_role_malformed", raw=str(content)[:300])
                return None
            label = label.strip().upper()
            if label not in ("SELF", "BYSTANDER", "EXONERATED"):
                log.warning("risk_llm_role_invalid_label", label=label, raw=str(content)[:300])
                return None

            log.info("risk_llm_role_classified", label=label)
            return label

        except Exception as exc:
            log.warning("risk_llm_role_failed", error=str(exc))
            return None

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

        # Group entities by client to generate risk events per client for this
        # document. Deduplicated by entity.id: an entity can have more than
        # one EntityMention row on the same document (mentioned multiple
        # times in the text), and without this the per-entity loop below
        # scores the same (client, document, entity) triple more than once.
        # Confirmed live: harmless before the LLM role gate (each redundant
        # pass produced the same deterministic score), but now each
        # redundant pass makes its own real LLM call, and _upsert_risk_event
        # lets whichever pass runs last win -- if an earlier pass got a real
        # classification and a later, purely-redundant pass then times out
        # and falls back unchanged, the final persisted score reverts to
        # the stale mechanical value even though the entity was correctly
        # classified moments earlier.
        client_to_entities = {}
        for m in mentions:
            bucket = client_to_entities.setdefault(m.entity.client_id, {})
            bucket[m.entity.id] = m.entity
        client_to_entities = {cid: list(ents.values()) for cid, ents in client_to_entities.items()}

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
        topic_conf = 0.0  # No real topic signal unless a topic passes the gate below -- was 1.0, a fabricated max-confidence default (FINDINGS.md #24)

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
        sentiment_conf = 0.0  # No real sentiment signal unless a DocumentSentiment row exists below -- same reasoning
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

                # LLM-assisted role gate: only for documents already scoring
                # above the LOW/MEDIUM boundary (see
                # RISK_ROLE_CLASSIFICATION_MIN_SCORE docstring). role is None
                # on ANY classification failure and is treated identically to
                # SELF -- the mechanical score is never touched by a missing
                # key, timeout, or malformed response, only by a confident
                # BYSTANDER/EXONERATED result.
                role_classification = None
                role_classification_attempted = final_score > self.RISK_ROLE_CLASSIFICATION_MIN_SCORE
                if role_classification_attempted:
                    role_classification = self._llm_classify_role(document, entity, client_id, run_id=run_id)
                    if role_classification in ("BYSTANDER", "EXONERATED"):
                        final_score = 0.0

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
                    "decision_reason": (
                        f"Risk level set to {self.get_risk_level(final_score)} based on topic '{top_topic}' "
                        f"(weight {topic_weight}), sentiment '{ent_sent_label}' (weight {ent_sent_weight}), "
                        f"trend '{trend_severity}' (weight {trend_weight}), and source reliability {source_reliability}."
                        if role_classification not in ("BYSTANDER", "EXONERATED")
                        else f"Mechanical score reduced to 0.0: LLM role classification found this entity is a {role_classification} in this document, not the actual subject of the negative story."
                    ),
                    "role_classification": role_classification,
                    "role_classification_source": (
                        "not_evaluated" if not role_classification_attempted
                        else ("llm" if role_classification else "fallback_unchanged")
                    ),
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
                    "explainability": explainability_data,
                    "computed_at": datetime.datetime.now(datetime.timezone.utc)
                }

                if persist:
                    write_result = self._upsert_risk_event(db, **payload)
                    if write_result == "skipped":
                        logger.info(
                            "risk_event_write_skipped_lower_quality",
                            run_id=run_id,
                            batch_id=batch_id,
                            worker_id=worker_id,
                            client_id=str(client_id),
                            document_id=str(document_id),
                            entity_id=str(entity.id),
                            incoming_role_source=explainability_data.get("role_classification_source"),
                        )
                    else:
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
                            processing_state="RISK_COMPLETE" if write_result == "inserted" else "RISK_UPDATED"
                        )
                else:
                    payloads.append(payload)

        return payloads
