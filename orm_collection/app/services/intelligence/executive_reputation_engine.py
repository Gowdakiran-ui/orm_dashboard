import datetime
import time
import os
import uuid
import math
import structlog
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.models.document import Document
from app.models.entity import Entity, EntityMention
from app.models.sentiment import DocumentSentiment
from app.models.risk import RiskEvent
from app.models.trends import TrendEvent
from app.models.narrative import Narrative
from app.models.executive_reputation import ExecutiveReputationScore
from app.models.client import Client
from app.models.alert import Alert

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────
# EXECUTIVE REPUTATION PROCESSING STATE MACHINE (R4)
# ─────────────────────────────────────────────────────────────
class ExecutiveReputationStateMachine:
    PENDING = "EXEC_REPUTATION_PENDING"
    PROCESSING = "EXEC_REPUTATION_PROCESSING"
    COMPLETE = "EXEC_REPUTATION_COMPLETE"
    FAILED = "EXEC_REPUTATION_FAILED"
    RETRYING = "EXEC_REPUTATION_RETRYING"
    SKIPPED = "EXEC_REPUTATION_SKIPPED"

    TRANSITIONS = {
        PENDING: {PROCESSING, SKIPPED},
        PROCESSING: {COMPLETE, FAILED, RETRYING, SKIPPED},
        RETRYING: {PROCESSING, FAILED, SKIPPED},
        FAILED: {PROCESSING, SKIPPED},
        COMPLETE: {PROCESSING, SKIPPED},
        SKIPPED: {PROCESSING}
    }

    @classmethod
    def is_valid_transition(cls, from_state: str, to_state: str) -> bool:
        allowed = cls.TRANSITIONS.get(from_state, set())
        return to_state in allowed

    @staticmethod
    def transition(
        db: Session,
        client: Client,
        to_state: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        failure_reason: Optional[str] = None,
        retry_count: Optional[int] = None,
        latency_ms: Optional[float] = None
    ) -> bool:
        from_state = client.exec_reputation_processing_status or ExecutiveReputationStateMachine.PENDING
        if not ExecutiveReputationStateMachine.is_valid_transition(from_state, to_state):
            logger.warning(
                "exec_reputation_invalid_state_transition",
                client_id=str(client.id),
                from_state=from_state,
                to_state=to_state
            )
            return False
        
        client.exec_reputation_processing_status = to_state
        if run_id is not None:
            client.exec_reputation_run_id = run_id
        if batch_id is not None:
            client.exec_reputation_batch_id = batch_id
        if failure_reason is not None:
            client.exec_reputation_failure_reason = str(failure_reason)[:4000]
        if retry_count is not None:
            client.exec_reputation_retry_count = retry_count
        if latency_ms is not None:
            client.exec_reputation_latency_ms = latency_ms
        if to_state == ExecutiveReputationStateMachine.FAILED:
            client.exec_reputation_failed_at = datetime.datetime.now(datetime.timezone.utc)
        return True


class ExecutiveReputationEngine:
    # E14-F1 — mirrors ReputationEngine/BenchmarkEngine's coverage rule: below
    # this share of the total weight mass, there is not enough signal to
    # state a real grade. Unlike ReputationScore, executive_reputation_scores'
    # score/grade/component columns are NOT NULL (see schema.sql), so a
    # no-evidence executive is written with the BenchmarkEngine pattern
    # instead (honest 0.0 sentinel + health_status="INSUFFICIENT_EVIDENCE"),
    # not an actual NULL.
    MIN_ACTIVE_WEIGHT = 0.20

    def __init__(self):
        self.weights = {
            "sentiment": 0.35,
            "risk": 0.30,
            "narrative": 0.15,
            "trend": 0.10,
            "visibility": 0.10
        }

    def _determine_grade(self, score: Optional[float]) -> Optional[str]:
        if score is None: return None
        if score >= 90: return "A+"
        if score >= 80: return "A"
        if score >= 70: return "B"
        if score >= 60: return "C"
        if score >= 40: return "D"
        return "F"


    def _determine_trend(self, current_score: Optional[float], previous_score: Optional[float]) -> str:
        if current_score is None:
            return "INSUFFICIENT_DATA"
        if previous_score is None:
            return "STABLE"
        diff = current_score - previous_score
        if diff >= 2.0:
            return "IMPROVING"
        elif diff <= -2.0:
            return "DECLINING"
        return "STABLE"

    def _calculate_source_reliability(self, url: Optional[str]) -> float:
        if not url:
            return 1.0
        try:
            domain = urlparse(url).netloc.lower()
            if any(x in domain for x in [".gov", ".nic.in", "court", "judiciary"]):
                return 1.20
            if any(x in domain for x in ["company", "corporate", "ir."]):
                return 1.10
            if any(x in domain for x in ["reuters.com", "bloomberg.com", "cnbc.com", "nytimes.com", "wsj.com"]):
                return 1.00
            if any(x in domain for x in ["reddit.com", "twitter.com", "facebook.com", "t.co"]):
                return 0.70
            if any(x in domain for x in ["blog", "medium.com", "substack"]):
                return 0.85
            return 0.95
        except Exception:
            return 1.0

    def calculate_executive_reputation(
        self,
        db: Session,
        client_id: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt: int = 0
    ):
        t0 = time.perf_counter()
        rid = run_id or uuid.uuid4().hex
        bid = batch_id or uuid.uuid4().hex[:12]
        wid = worker_id or str(os.getpid())

        log = logger.bind(
            run_id=rid,
            batch_id=bid,
            worker_id=wid,
            client_id=client_id,
            attempt=attempt,
            processing_stage="EXEC_REPUTATION_CALCULATION"
        )
        log.info("exec_reputation_calculation_started")

        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            log.error("exec_reputation_client_not_found")
            raise ValueError(f"Client {client_id} not found")

        # R1: Strictly only evaluate entities where entity_type == "person"
        executives = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "person"
        ).all()
        
        if not executives:
            log.info("exec_reputation_no_executives_found_skipping")
            ExecutiveReputationStateMachine.transition(
                db, client, ExecutiveReputationStateMachine.SKIPPED,
                run_id=rid, batch_id=bid
            )
            db.commit()
            return

        exec_ids = [e.id for e in executives]
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        lookback_date = now_utc - datetime.timedelta(days=30)

        # P3: Batch preloading of all executive mentions, risks, trends, alerts, and narratives
        mentions = db.query(EntityMention).filter(
            EntityMention.entity_id.in_(exec_ids),
            EntityMention.created_at >= lookback_date
        ).all()

        # Group mentions by executive entity_id
        mention_map = {eid: [] for eid in exec_ids}
        for m in mentions:
            mention_map[m.entity_id].append(m)

        all_doc_ids = list(set(m.document_id for m in mentions))
        
        # Batch preload document URLs & sentiments in O(1) maps
        doc_url_map = {}
        sentiment_map = {}
        if all_doc_ids:
            docs = db.query(Document.id, Document.url).filter(Document.id.in_(all_doc_ids)).all()
            doc_url_map = {d[0]: d[1] for d in docs}

            sents = db.query(DocumentSentiment.document_id, DocumentSentiment.sentiment_score).filter(
                DocumentSentiment.document_id.in_(all_doc_ids)
            ).all()
            sentiment_map = {s[0]: s[1] for s in sents}

        # Batch preload risks
        risks = db.query(RiskEvent).filter(
            RiskEvent.client_id == client_id,
            RiskEvent.entity_id.in_(exec_ids),
            RiskEvent.created_at >= lookback_date
        ).all()
        risk_map = {eid: [] for eid in exec_ids}
        for r in risks:
            risk_map[r.entity_id].append(r)

        # Batch preload trends
        trends = db.query(TrendEvent).filter(
            TrendEvent.client_id == client_id,
            TrendEvent.entity_id.in_(exec_ids),
            TrendEvent.created_at >= lookback_date
        ).all()
        trend_map = {eid: [] for eid in exec_ids}
        for t in trends:
            trend_map[t.entity_id].append(t)

        # Batch preload narratives (shared pool)
        narratives = db.query(Narrative).filter(
            Narrative.client_id == client_id,
            Narrative.updated_at >= lookback_date
        ).all()

        # Batch preload alerts (shared pool)
        alerts = db.query(Alert).filter(
            Alert.client_id == client_id,
            Alert.created_at >= lookback_date
        ).all()

        # Loop over matching executives and calculate scores using preloaded maps
        for exec_entity in executives:
            savepoint = db.begin_nested()
            try:
                # Extract preloaded lists
                exec_mentions = mention_map.get(exec_entity.id, [])
                exec_doc_ids = list(set(m.document_id for m in exec_mentions))
                exec_doc_urls = [doc_url_map[did] for did in exec_doc_ids if did in doc_url_map and doc_url_map[did]]
                exec_risks = risk_map.get(exec_entity.id, [])
                exec_trends = trend_map.get(exec_entity.id, [])
                
                self._evaluate_single_executive_optimized(
                    db, client_id, exec_entity,
                    exec_doc_ids, exec_doc_urls, exec_risks, exec_trends, narratives, alerts, sentiment_map,
                    run_id=rid, batch_id=bid, worker_id=wid, attempt=attempt
                )
                savepoint.commit()
            except Exception as e:
                savepoint.rollback()
                log.error("exec_reputation_individual_failed", exec_name=exec_entity.name, error=str(e))

        elapsed_ms = (time.perf_counter() - t0) * 1000
        log.info("exec_reputation_calculation_complete", total_latency_ms=round(elapsed_ms, 2))

    def _evaluate_single_executive_optimized(
        self,
        db: Session,
        client_id: str,
        exec_entity: Entity,
        doc_ids: List[str],
        doc_urls: List[str],
        supporting_risks: List[RiskEvent],
        supporting_trends: List[TrendEvent],
        all_narratives: List[Narrative],
        supporting_alerts: List[Alert],
        sentiment_map: Dict[str, float],
        run_id: str,
        batch_id: str,
        worker_id: str,
        attempt: int
    ):
        t_start = time.perf_counter()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        one_day_ago = now_utc - datetime.timedelta(days=1)

        # 1. Executive Sentiment (None when there's no evidence to compute it from)
        sentiment_component = None
        avg_sentiment = None
        if doc_ids:
            sent_scores = [sentiment_map[did] for did in doc_ids if did in sentiment_map]
            if sent_scores:
                avg_sentiment = sum(sent_scores) / len(sent_scores)
                sentiment_component = ((avg_sentiment + 1.0) / 2.0) * 100.0

        # 2. Executive Risk
        risk_component = None
        if supporting_risks:
            avg_risk = sum(r.risk_score for r in supporting_risks) / len(supporting_risks)
            risk_component = 100.0 - avg_risk

        # 3. Executive Narratives
        supporting_narratives = []
        narrative_penalty = 0
        top_positive = None
        top_negative = None
        max_pos = -1.0
        min_neg = 1.0

        for n in all_narratives:
            meta = n.evidence_metadata or {}
            entities_in_narrative = meta.get("supporting_entities", [])
            if str(exec_entity.id) in entities_in_narrative or exec_entity.name.lower() in n.narrative_name.lower():
                supporting_narratives.append(n)
                if n.sentiment_score < 0 and n.status in ["GROWING", "PEAK"]:
                    narrative_penalty += 20
                elif n.sentiment_score > 0 and n.status in ["GROWING", "PEAK"]:
                    narrative_penalty -= 10

                if n.sentiment_score > max_pos:
                    max_pos = n.sentiment_score
                    top_positive = n.narrative_name
                if n.sentiment_score < min_neg:
                    min_neg = n.sentiment_score
                    top_negative = n.narrative_name

        narrative_component = None
        if supporting_narratives:
            narrative_component = max(0.0, min(100.0, 100.0 - narrative_penalty))

        # 4. Executive Trend
        trend_component = None
        # Sort preloaded trends by date and limit to 10
        sorted_trends = sorted(supporting_trends, key=lambda x: x.created_at, reverse=True)[:10]
        if sorted_trends:
            trend_val = 50.0
            for t in sorted_trends:
                if t.severity in ["HIGH", "CRITICAL"]:
                    if (avg_sentiment or 0.0) < 0:
                        trend_val -= 15
                    else:
                        trend_val += 15
            trend_component = max(0.0, min(100.0, trend_val))

        # 5. Executive Visibility
        # Count mentions in-memory (E14-F3: no floor -- 0 mentions means the
        # component is simply unavailable, same as every other component
        # above, instead of outscoring a barely-covered executive)
        total_mentions = len(doc_ids) # Or sum mention_counts if available. Let's use doc_ids count for consistency
        visibility_component = None
        if total_mentions > 0:
            visibility_component = min(100.0, (total_mentions / 500.0) * 100.0)

        # E14-F1: Dynamic Weight Normalization -- components that could not be
        # computed are dropped and the remaining weights renormalized, same
        # rule ReputationEngine/BenchmarkEngine already use. has_evidence
        # gates whether a real score/grade is produced at all.
        components = {
            "sentiment": sentiment_component,
            "risk": risk_component,
            "narrative": narrative_component,
            "trend": trend_component,
            "visibility": visibility_component,
        }
        active_weight = sum(self.weights[k] for k, v in components.items() if v is not None)
        has_evidence = active_weight >= self.MIN_ACTIVE_WEIGHT

        # A3: Dynamic Source Reliability
        source_reliability = 1.0
        if doc_urls:
            reliabilities = [self._calculate_source_reliability(url) for url in doc_urls]
            source_reliability = sum(reliabilities) / len(reliabilities)

        if has_evidence:
            weighted_sum = sum(v * self.weights[k] for k, v in components.items() if v is not None)
            base_score = weighted_sum / active_weight
            final_score = max(0.0, min(100.0, base_score * source_reliability))
            grade = self._determine_grade(final_score)
        else:
            # No plausible-looking number without evidence (E14-F1). Mirrors
            # BenchmarkEngine's zero-evidence handling: executive_reputation_scores'
            # score/grade columns are NOT NULL (unlike reputation_scores), so
            # this is an honest 0.0 sentinel + health_status flag below, not a
            # fabricated grade -- "NA" is not one of the real A+/A/B/C/D/F values.
            final_score = 0.0
            grade = "NA"

        # Get previous score
        prev_reputation = db.query(ExecutiveReputationScore).filter(
            ExecutiveReputationScore.entity_id == exec_entity.id
        ).order_by(ExecutiveReputationScore.created_at.desc()).first()

        prev_score = prev_reputation.score if prev_reputation else None
        rep_trend = self._determine_trend(final_score if has_evidence else None, prev_score)

        # A7: Upstream Health Status Checking
        has_recent_risk = any(r.created_at >= one_day_ago for r in supporting_risks)
        has_recent_trend = any(t.created_at >= one_day_ago for t in sorted_trends)

        if not has_evidence:
            health_status = "INSUFFICIENT_EVIDENCE"
        elif not (has_recent_risk and has_recent_trend):
            health_status = "PARTIAL"
        else:
            health_status = "COMPLETE"

        # A6: Executive Confidence Score (E14-F2: already genuinely scoped to
        # this executive's own doc_ids/supporting_risks/supporting_trends --
        # see data_coverage_val below, which now reuses this instead of an
        # unrelated client-wide constant)
        doc_confidence = min(len(doc_ids) / 10.0, 1.0)
        signal_completeness = (1.0 if has_recent_risk else 0.5) * 0.5 + (1.0 if has_recent_trend else 0.5) * 0.5
        confidence_score = round(doc_confidence * 0.6 + signal_completeness * 0.4, 4) if has_evidence else 0.0

        # A4: Mathematical Lineage
        calculation_lineage = {
            "formula": "Weighted Sum of Available Components / Total Available Weights, then * SourceReliability",
            "component_scores": {
                "sentiment": round(sentiment_component, 2) if sentiment_component is not None else None,
                "risk": round(risk_component, 2) if risk_component is not None else None,
                "narrative": round(narrative_component, 2) if narrative_component is not None else None,
                "trend": round(trend_component, 2) if trend_component is not None else None,
                "visibility": round(visibility_component, 2) if visibility_component is not None else None
            },
            "component_weights": self.weights,
            "active_weight_sum": round(active_weight, 4),
            "source_reliability": round(source_reliability, 4),
            "raw_values": {
                "avg_sentiment": round(avg_sentiment, 4) if avg_sentiment is not None else None,
                "total_mentions": total_mentions,
                "document_count": len(doc_ids)
            },
            "confidence_calculation": {
                "doc_confidence": round(doc_confidence, 4),
                "signal_completeness": round(signal_completeness, 4)
            },
            "decision_reason": (
                f"Insufficient evidence: active weight {active_weight:.2f} < "
                f"{self.MIN_ACTIVE_WEIGHT:.2f}; no grade stated."
                if not has_evidence else
                f"Executive reputation calculated dynamically over 30-day window with health state: {health_status}."
            )
        }

        # A5: Evidence Metadata
        evidence_metadata = {
            "supporting_documents": [str(did) for did in doc_ids],
            "supporting_risks": [str(r.id) for r in supporting_risks],
            "supporting_trends": [str(t.id) for t in sorted_trends],
            "supporting_alerts": [str(a.id) for a in supporting_alerts],
            "supporting_narratives": [str(n.id) for n in supporting_narratives],
            "supporting_executive_entity": str(exec_entity.id)
        }

        latency_ms = (time.perf_counter() - t_start) * 1000

        # E14-F2: real per-executive coverage instead of a client-wide
        # constant derived from which source *types* are active platform-wide
        # (identical for every executive of every client). Mirrors
        # ReputationEngine/BenchmarkEngine, which both set data_coverage to
        # their own confidence_score.
        data_coverage_val = confidence_score

        # executive_reputation_scores' component columns are NOT NULL
        # (schema.sql), unlike reputation_scores'. 0.0 here means "component
        # unavailable" for storage purposes only -- the true None is what
        # calculation_lineage's component_scores dict records, and is what
        # active_weight/has_evidence above were computed from.
        sentiment_component_db = sentiment_component if sentiment_component is not None else 0.0
        risk_component_db = risk_component if risk_component is not None else 0.0
        narrative_component_db = narrative_component if narrative_component is not None else 0.0
        trend_component_db = trend_component if trend_component is not None else 0.0
        visibility_component_db = visibility_component if visibility_component is not None else 0.0

        # R7: Duplicate protection using ON CONFLICT DO UPDATE on uq_exec_reputation_run
        stmt = insert(ExecutiveReputationScore).values(
            id=uuid.uuid4(),
            client_id=client_id,
            entity_id=exec_entity.id,
            executive_name=exec_entity.name,
            score=final_score,
            grade=grade,
            sentiment_component=sentiment_component_db,
            risk_component=risk_component_db,
            narrative_component=narrative_component_db,
            trend_component=trend_component_db,
            visibility_component=visibility_component_db,
            confidence_score=confidence_score,
            reputation_trend=rep_trend,
            top_positive_narrative=top_positive,
            top_negative_narrative=top_negative,
            run_id=run_id,
            batch_id=batch_id,
            worker_id=worker_id,
            latency_ms=latency_ms,
            retry_count=attempt,
            evidence_metadata=evidence_metadata,
            calculation_lineage=calculation_lineage,
            health_status=health_status,
            data_coverage=data_coverage_val
        ).on_conflict_do_update(
            constraint="uq_exec_reputation_run",
            set_={
                "score": final_score,
                "grade": grade,
                "sentiment_component": sentiment_component_db,
                "risk_component": risk_component_db,
                "narrative_component": narrative_component_db,
                "trend_component": trend_component_db,
                "visibility_component": visibility_component_db,
                "confidence_score": confidence_score,
                "reputation_trend": rep_trend,
                "top_positive_narrative": top_positive,
                "top_negative_narrative": top_negative,
                "batch_id": batch_id,
                "worker_id": worker_id,
                "latency_ms": latency_ms,
                "retry_count": attempt,
                "evidence_metadata": evidence_metadata,
                "calculation_lineage": calculation_lineage,
                "health_status": health_status,
                "data_coverage": data_coverage_val
            }
        )
        db.execute(stmt)

    def process_client(
        self,
        db: Session,
        client_id: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt: int = 0
    ):
        self.calculate_executive_reputation(
            db,
            client_id,
            run_id=run_id,
            batch_id=batch_id,
            worker_id=worker_id,
            attempt=attempt
        )
