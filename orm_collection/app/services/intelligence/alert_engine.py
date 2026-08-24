import datetime
import time
import os
import uuid
import traceback
import structlog
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models.risk import RiskEvent
from app.models.trends import TrendEvent
from app.models.alert import Alert
from app.models.entity import Entity
from app.models.client import Client
from app.models.alert_state import AlertClientState

logger = structlog.get_logger()

VALID_ALERT_TRANSITIONS = {
    "ALERT_PENDING": {"ALERT_PROCESSING"},
    "ALERT_PROCESSING": {"ALERT_COMPLETE", "ALERT_FAILED", "ALERT_RETRYING", "ALERT_SKIPPED"},
    "ALERT_COMPLETE": {"ALERT_PROCESSING"},
    "ALERT_FAILED": {"ALERT_RETRYING", "ALERT_PROCESSING"},
    "ALERT_RETRYING": {"ALERT_PROCESSING"},
    "ALERT_SKIPPED": {"ALERT_PROCESSING"},
}

VALID_LIFECYCLE_TRANSITIONS = {
    "NEW": {"ACTIVE", "ACKNOWLEDGED", "CLOSED"},
    "ACTIVE": {"ACKNOWLEDGED", "RESOLVED", "CLOSED"},
    "ACKNOWLEDGED": {"RESOLVED", "CLOSED"},
    "RESOLVED": {"CLOSED", "ACTIVE"},
    "CLOSED": {"ACTIVE"},
}

SEVERITY_RANK = {
    "INFO": 1,
    "WARNING": 2,
    "HIGH": 3,
    "CRITICAL": 4
}


def _is_transient_error(exc: Exception) -> bool:
    """Identify transient database or network errors suitable for retry."""
    msg = str(exc).lower()
    transient_indicators = [
        "timeout", "lock", "deadlock", "connection", "read-only",
        "command timeout", "serialization", "temporarily", "operationalerror",
        "connection refused", "psycopg2.operationalerror"
    ]
    return any(indicator in msg for indicator in transient_indicators)


class AlertEngine:
    def __init__(self):
        self.trend_threshold = 50.0
        self.sentiment_threshold = 50.0
        self._threshold_cache = {}  # P7: Cached dynamic thresholds to avoid re-querying count

    # ------------------------------------------------------------------
    # R2 — State Machine Helpers
    # ------------------------------------------------------------------
    def _get_or_create_state(self, db: Session, client_id: str) -> AlertClientState:
        """Retrieve or initialize an AlertClientState row for this client."""
        state = db.query(AlertClientState).filter(
            AlertClientState.client_id == client_id
        ).first()
        if not state:
            state = AlertClientState(
                client_id=client_id,
                processing_status="ALERT_PENDING",
                retry_count=0
            )
            db.add(state)
            db.flush()
        return state

    def _transition_state(
        self,
        db: Session,
        state: AlertClientState,
        new_status: str,
        run_id: str = None,
        batch_id: str = None,
        error: str = None,
        log=None
    ):
        """Apply a validated state transition with logger audit."""
        current = state.processing_status
        allowed = VALID_ALERT_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            if log:
                log.warning(
                    "alert_invalid_state_transition",
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
    # A2 — Dynamic Thresholds (Cached to satisfy P7)
    # ------------------------------------------------------------------
    def _get_dynamic_evidence_threshold(self, db: Session, client_id: str) -> float:
        """Calculate dynamic evidence threshold based on client volatility/history (with cache lookup)."""
        if client_id in self._threshold_cache:
            return self._threshold_cache[client_id]

        trend_count = db.query(TrendEvent).filter(TrendEvent.client_id == client_id).count()
        risk_count = db.query(RiskEvent).filter(RiskEvent.client_id == client_id).count()
        total_signals = trend_count + risk_count

        if total_signals > 50:
            threshold = 55.0
        elif total_signals > 15:
            threshold = 40.0
        else:
            threshold = 15.0

        self._threshold_cache[client_id] = threshold
        return threshold

    # ------------------------------------------------------------------
    # A4 — Alert Confidence Score Calculation
    # ------------------------------------------------------------------
    def _calculate_confidence(self, agreement: float, doc_count: int, max_risk: float, max_trend: float) -> float:
        """Calculate Alert Confidence based on multi-engine parameters."""
        agreement_factor = agreement * 40.0
        doc_factor = min(doc_count * 6.0, 30.0)
        signal_strength = (max(max_risk, 0.0) * 0.15) + (min(max_trend, 1000.0) * 0.015)
        raw_score = agreement_factor + doc_factor + signal_strength
        return min(max(raw_score, 10.0), 100.0)

    # ------------------------------------------------------------------
    # A8 — Human-Readable Summary (Analyst Quality)
    # ------------------------------------------------------------------
    def _generate_human_summary(
        self,
        client_name: str,
        entity_name: str,
        risks_count: int,
        trends_count: int,
        evidence_score: float,
        confidence_score: float,
        is_exec: bool,
        doc_count: int
    ) -> str:
        """Generate human summary for analysts answering critical questions."""
        exec_str = "Yes (Executive involved)" if is_exec else "No"
        importance = "CRITICAL escalation required." if evidence_score > 70 else "HIGH priority monitoring."
        if is_exec:
            importance = "CRITICAL - Executive risk involvement detected."

        summary = (
            f"Why did this happen?\n"
            f"Multiple intelligence signals crossed safety limits. We detected {risks_count} risk events and {trends_count} trend events correlating to entity '{entity_name}'.\n\n"
            f"What changed?\n"
            f"Combined evidence score is {evidence_score:.1f} (Confidence: {confidence_score:.1f}%).\n\n"
            f"How many documents support it?\n"
            f"Supported by {doc_count} unique documents.\n\n"
            f"Which executives are involved?\n"
            f"Executive Involvement: {exec_str}.\n\n"
            f"Why is this important?\n"
            f"Entity '{entity_name}' shows active risk indicators. {importance}\n\n"
            f"What should the analyst investigate?\n"
            f"Review the associated {doc_count} document sources, check latest risk factors, and monitor media trends for '{entity_name}'."
        )
        return summary

    # ------------------------------------------------------------------
    # A3 Suppression & A7 Escalation Upsert logic (P3 Optimized with Cache Map)
    # ------------------------------------------------------------------
    def _upsert_hardened_alert(self, db: Session, existing_map: dict = None, **kwargs) -> Alert:
        """
        Idempotent and dynamic write for Alert.
        Implements A3 suppression (living incidents) and A7 automatic escalation.
        P3 Database Optimization: Leverages in-memory existing_map to avoid N+1 queries.
        """
        client_id = kwargs["client_id"]
        alert_type = kwargs["alert_type"]
        entity_id = kwargs.get("entity_id")
        document_id = kwargs.get("document_id")
        new_severity = kwargs.get("severity", "WARNING")
        new_evidence = kwargs.get("evidence_score", 0.0)
        new_confidence = kwargs.get("confidence_score", 0.0)
        new_docs = kwargs.get("explainability", {}).get("contributing_documents", [])

        lookup_key = (alert_type, entity_id, document_id)
        existing = None

        if existing_map is not None:
            existing = existing_map.get(lookup_key)
        else:
            # Fallback direct query if map is not provided
            query = db.query(Alert).filter(
                Alert.client_id == client_id,
                Alert.alert_type == alert_type
            )
            if entity_id is not None:
                query = query.filter(Alert.entity_id == entity_id)
            else:
                query = query.filter(Alert.entity_id == None)  # noqa: E711

            if document_id is not None:
                query = query.filter(Alert.document_id == document_id)
            else:
                query = query.filter(Alert.document_id == None)  # noqa: E711
            existing = query.first()

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if existing:
            # A7: Escalation checks
            old_sev = existing.severity
            esc_hist = existing.escalation_history or []
            if SEVERITY_RANK.get(new_severity, 0) > SEVERITY_RANK.get(old_sev, 0):
                existing.severity = new_severity
                esc_hist.append({
                    "from_severity": old_sev,
                    "to_severity": new_severity,
                    "timestamp": now_str,
                    "reason": f"Evidence score increased to {new_evidence:.1f}"
                })
                existing.escalation_history = esc_hist

            # A3: Merge documents and update article count
            existing_docs = existing.explainability.get("contributing_documents", []) if existing.explainability else []
            merged_docs = list(set(existing_docs + new_docs))
            existing.article_count = len(merged_docs)

            # Update scores & metadata
            # Defensive clamp mirrors the compute-site clamp above -- new_evidence should
            # already be <=100 by the time it reaches here, but this guards the same
            # ck_alerts_evidence_score bound against any other caller of this upsert.
            existing.evidence_score = min(max(existing.evidence_score or 0.0, new_evidence), 100.0)
            existing.confidence_score = max(existing.confidence_score or 0.0, new_confidence)
            existing.trigger_value = kwargs.get("trigger_value", existing.trigger_value)
            existing.run_id = kwargs.get("run_id", existing.run_id)
            existing.batch_id = kwargs.get("batch_id", existing.batch_id)
            existing.worker_id = kwargs.get("worker_id", existing.worker_id)
            existing.latency_ms = kwargs.get("latency_ms", existing.latency_ms)

            # A6: Lifecycle state progression (re-open closed/resolved incidents to ACTIVE on new evidence)
            if existing.lifecycle_status in ["RESOLVED", "CLOSED"]:
                old_status = existing.lifecycle_status
                existing.lifecycle_status = "ACTIVE"
                l_hist = existing.lifecycle_history or []
                l_hist.append({
                    "from_status": old_status,
                    "to_status": "ACTIVE",
                    "timestamp": now_str,
                    "reason": "New supporting evidence received"
                })
                existing.lifecycle_history = l_hist

            # Update explainability & human summary
            existing.explainability = kwargs.get("explainability", existing.explainability)
            existing.human_summary = kwargs.get("human_summary", existing.human_summary)
            existing.description = kwargs.get("description", existing.description)

            # Record running state history
            hist = existing.state_history or []
            hist.append({"state": "ALERT_PROCESSING", "time": now_str})
            hist.append({"state": "ALERT_COMPLETE", "time": now_str})
            existing.state_history = hist

            db.flush()
            return existing

        # Create new alert with initial lifecycle NEW
        kwargs["lifecycle_status"] = "NEW"
        kwargs["lifecycle_history"] = [{"status": "NEW", "timestamp": now_str, "reason": "Initial alert generation"}]
        kwargs["article_count"] = len(new_docs)

        alert = Alert(**kwargs)
        db.add(alert)
        db.flush()
        
        # Populate back to cache map if provided
        if existing_map is not None:
            existing_map[lookup_key] = alert

        return alert

    # ------------------------------------------------------------------
    # A1 — Multi-Signal Alert Decision & Validation Entrypoint
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
        Execute accuracy-hardened alert generation for a client.
        P3 Optimized: Pre-fetches all matching Entities and existing Alert configurations to achieve O(1) loop evaluations.
        """
        run_id = run_id or uuid.uuid4().hex
        batch_id = batch_id or uuid.uuid4().hex[:12]
        worker_id = str(os.getpid())
        t_start = time.perf_counter()

        log = logger.bind(
            run_id=run_id,
            batch_id=batch_id,
            client_id=str(client_id),
            worker_id=worker_id,
            task="process_client_alerts"
        )

        # Transition: → ALERT_PROCESSING
        state = self._get_or_create_state(db, client_id)
        self._transition_state(db, state, "ALERT_PROCESSING", run_id, batch_id, log=log)
        db.commit()

        log.info("alert_client_started", processing_state="ALERT_PROCESSING")

        try:
            alerts_count = 0
            client_obj = db.query(Client).filter(Client.id == client_id).first()
            client_name = client_obj.name if client_obj else "Unknown"

            # 1. Fetch raw signals in bulk
            recent_risks = db.query(RiskEvent).filter(
                RiskEvent.client_id == client_id,
                RiskEvent.risk_score > 50
            ).order_by(RiskEvent.created_at.desc()).limit(15).all()

            recent_trends = db.query(TrendEvent).filter(
                TrendEvent.client_id == client_id,
                TrendEvent.percentage_change > 30.0
            ).order_by(TrendEvent.created_at.desc()).limit(15).all()

            exec_risks = db.query(RiskEvent, Entity).join(Entity, Entity.id == RiskEvent.entity_id).filter(
                RiskEvent.client_id == client_id,
                RiskEvent.risk_score > 50
            ).all()

            # 2. Group signals by entity_id
            groups = {}
            
            # Map risk entities
            for risk in recent_risks:
                eid = risk.entity_id
                if not eid:
                    continue
                if eid not in groups:
                    groups[eid] = {"risks": [], "trends": [], "executives": []}
                groups[eid]["risks"].append(risk)

            # Map trend entities
            for trend in recent_trends:
                eid = trend.entity_id
                if not eid:
                    continue
                if eid not in groups:
                    groups[eid] = {"risks": [], "trends": [], "executives": []}
                groups[eid]["trends"].append(trend)

            # Map executive risks
            for r, ent in exec_risks:
                is_exec = "CEO" in ent.name.upper() or "EXECUTIVE" in ent.name.upper()
                if is_exec:
                    eid = r.entity_id
                    if eid not in groups:
                        groups[eid] = {"risks": [], "trends": [], "executives": []}
                    groups[eid]["executives"].append((r, ent))

            # P3 Optimization: Pre-fetch all matching Entities to eliminate N+1 queries
            entity_ids = list(groups.keys())
            entities_map = {}
            if entity_ids:
                entities_list = db.query(Entity).filter(Entity.id.in_(entity_ids)).all()
                entities_map = {ent.id: ent for ent in entities_list}

            # P3 Optimization: Pre-fetch all existing Alerts to eliminate N+1 lookup queries
            existing_alerts = db.query(Alert).filter(Alert.client_id == client_id).all()
            existing_map = {}
            for a in existing_alerts:
                existing_map[(a.alert_type, a.entity_id, a.document_id)] = a

            # 3. Dynamic evidence threshold
            evidence_threshold = self._get_dynamic_evidence_threshold(db, client_id)

            # 4. Evaluate each grouped entity
            for eid, data in groups.items():
                try:
                    # P3 Lookup: In-memory instead of query
                    entity_obj = entities_map.get(eid)
                    entity_name = entity_obj.name if entity_obj else "Unnamed Entity"

                    # Calculate max scores
                    max_risk = max([r.risk_score for r in data["risks"]], default=0.0)
                    max_trend = max([t.percentage_change for t in data["trends"]], default=0.0)
                    is_exec = len(data["executives"]) > 0

                    # Documents collection
                    docs_set = set()
                    for r in data["risks"]:
                        if r.document_id:
                            docs_set.add(str(r.document_id))
                    for t in data["trends"]:
                        t_docs = t.triggering_documents or []
                        for td in t_docs:
                            docs_set.add(str(td))

                    doc_list = list(docs_set)
                    doc_count = len(doc_list)

                    # A1: Calculate evidence score
                    evidence_score = 0.0
                    if max_risk > 0.0:
                        evidence_score += max_risk * 0.45
                    if max_trend > 0.0:
                        evidence_score += min(max_trend * 0.25, 20.0)
                    if len(data["risks"]) > 0 and len(data["trends"]) > 0:
                        evidence_score += 15.0  # Correlation bonus
                    evidence_score += min(doc_count * 4.0, 20.0)  # Document weight
                    if is_exec:
                        evidence_score += 15.0  # Executive weight
                    # Components can sum above 100 (max risk 45 + trend 20 + correlation 15
                    # + doc weight 20 + exec weight 15 = 115) -- clamp to match
                    # ck_alerts_evidence_score's 0-100 bound (database/schema.sql). No floor
                    # needed here (unlike confidence_score's 10.0 floor): every term above is
                    # a non-negative additive contribution, so evidence_score can't go below 0.
                    evidence_score = min(evidence_score, 100.0)

                    # A4: Calculate confidence score
                    agreement = 1.0 if (len(data["risks"]) > 0 and len(data["trends"]) > 0) else 0.5
                    confidence_score = self._calculate_confidence(agreement, doc_count, max_risk, max_trend)

                    # Filter: Only generate if evidence score and confidence pass thresholds
                    if evidence_score >= evidence_threshold and confidence_score >= 40.0:
                        # Determine severity
                        severity = "WARNING"
                        if evidence_score > 70.0 or is_exec:
                            severity = "CRITICAL"
                        elif evidence_score > 45.0:
                            severity = "HIGH"

                        # Determine type
                        alert_type = "Multi-Signal Incident"
                        if is_exec:
                            alert_type = "Executive Risk"

                        # A8: Generate analyst summary
                        human_summary = self._generate_human_summary(
                            client_name, entity_name, len(data["risks"]), len(data["trends"]),
                            evidence_score, confidence_score, is_exec, doc_count
                        )

                        # A5: Explainability structure
                        explainability = {
                            "why_it_fired": f"Entity '{entity_name}' exceeded dynamic client evidence threshold of {evidence_threshold:.1f}.",
                            "contributing_engines": ["Risk" if max_risk > 0.0 else None, "Trend" if max_trend > 0.0 else None],
                            "contributing_documents": doc_list,
                            "contributing_entities": [str(eid)],
                            "contributing_topics": [],
                            "contributing_trends": [str(t.id) for t in data["trends"]],
                            "contributing_risks": [str(r.id) for r in data["risks"]],
                            "supporting_evidence": {
                                "max_risk_score": max_risk,
                                "max_trend_change": max_trend,
                                "document_count": doc_count,
                                "executive_involved": is_exec
                            },
                            "confidence_calculation": {
                                "agreement_factor": agreement * 40.0,
                                "document_factor": min(doc_count * 6.0, 30.0),
                                "max_risk": max_risk,
                                "max_trend": max_trend,
                                "final_score": confidence_score
                            },
                            "decision_reason": f"Combined evidence score of {evidence_score:.1f} meets the dynamic client threshold."
                        }

                        # Clean null values from engines list
                        explainability["contributing_engines"] = [e for e in explainability["contributing_engines"] if e]

                        # Upsert Alert (P3 Optimized with memory lookup map)
                        self._upsert_hardened_alert(
                            db,
                            existing_map=existing_map,
                            client_id=client_id,
                            entity_id=eid,
                            document_id=None,
                            alert_type=alert_type,
                            severity=severity,
                            title=f"Multi-Signal Incident: {entity_name}",
                            description=human_summary,
                            trigger_value=evidence_score,
                            baseline_value=evidence_threshold,
                            confidence_score=confidence_score,
                            evidence_score=evidence_score,
                            supporting_signals={
                                "risks_count": len(data["risks"]),
                                "trends_count": len(data["trends"])
                            },
                            explainability=explainability,
                            human_summary=human_summary,
                            processing_status="ALERT_COMPLETE",
                            run_id=run_id,
                            batch_id=batch_id,
                            worker_id=worker_id,
                            state_history=[
                                {"state": "ALERT_PROCESSING", "time": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                                {"state": "ALERT_COMPLETE", "time": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                            ]
                        )
                        alerts_count += 1
                except Exception as eval_exc:
                    logger.error("alert_entity_evaluation_failed", entity_id=str(eid), error=str(eval_exc))

            # R1: Commit the entire successful batch together
            db.commit()

            # Transition: → ALERT_COMPLETE or ALERT_SKIPPED
            state = self._get_or_create_state(db, client_id)
            final_status = "ALERT_SKIPPED" if alerts_count == 0 else "ALERT_COMPLETE"
            self._transition_state(db, state, final_status, run_id, batch_id, log=log)
            state.last_run_at = datetime.datetime.now(datetime.timezone.utc)
            state.last_success_at = datetime.datetime.now(datetime.timezone.utc)
            state.retry_count = 0
            state.last_error = None
            db.commit()

            # Update latency_ms for all generated alerts
            latency_ms = (time.perf_counter() - t_start) * 1000
            if alerts_count > 0:
                db.query(Alert).filter(
                    Alert.client_id == client_id,
                    Alert.run_id == run_id
                ).update({Alert.latency_ms: latency_ms}, synchronize_session=False)
                db.commit()

            log.info(
                "alert_client_completed",
                processing_state=final_status,
                alerts_generated=alerts_count,
                latency_ms=round(latency_ms, 2)
            )
            return alerts_count

        except Exception as batch_exc:
            db.rollback()

            latency_ms = (time.perf_counter() - t_start) * 1000
            is_transient = _is_transient_error(batch_exc)
            
            try:
                state = self._get_or_create_state(db, client_id)
                if is_transient and attempt < 3:
                    self._transition_state(db, state, "ALERT_RETRYING", run_id, batch_id, error=str(batch_exc), log=log)
                    state.retry_count = attempt
                    state.last_retry_at = datetime.datetime.now(datetime.timezone.utc)
                else:
                    self._transition_state(db, state, "ALERT_FAILED", run_id, batch_id, error=str(batch_exc), log=log)
                    state.retry_count = attempt
                state.last_run_at = datetime.datetime.now(datetime.timezone.utc)
                db.commit()
            except Exception as state_exc:
                db.rollback()
                log.error("alert_state_update_failed", error=str(state_exc))

            log.error(
                "alert_client_failed",
                processing_state="ALERT_FAILED" if not is_transient or attempt >= 3 else "ALERT_RETRYING",
                error=str(batch_exc),
                traceback=traceback.format_exc(),
                latency_ms=round(latency_ms, 2),
                retry_count=attempt
            )
            raise batch_exc

    # ------------------------------------------------------------------
    # Backwards-compatible Wrappers
    # ------------------------------------------------------------------
    def evaluate_risk_alerts(self, db: Session, client_id: str, run_id: str, batch_id: str, worker_id: str, attempt: int) -> int:
        return 0

    def evaluate_trend_alerts(self, db: Session, client_id: str, run_id: str, batch_id: str, worker_id: str, attempt: int) -> int:
        return 0

    def evaluate_executive_alerts(self, db: Session, client_id: str, run_id: str, batch_id: str, worker_id: str, attempt: int) -> int:
        return 0

    def evaluate_all(self, db: Session, client_id: str):
        """Legacy helper for backwards compatibility."""
        self.process_client(db, client_id)
