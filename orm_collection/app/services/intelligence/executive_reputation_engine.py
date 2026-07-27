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


    def _determine_trend(self, current_score: float, previous_score: float) -> str:
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

        # 1. Executive Sentiment
        sentiment_component = 50.0
        avg_sentiment = 0.0
        if doc_ids:
            sent_scores = [sentiment_map[did] for did in doc_ids if did in sentiment_map]
            if sent_scores:
                avg_sentiment = sum(sent_scores) / len(sent_scores)
                sentiment_component = ((avg_sentiment + 1.0) / 2.0) * 100.0

        # 2. Executive Risk
        avg_risk = sum(r.risk_score for r in supporting_risks) / len(supporting_risks) if supporting_risks else 0.0
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

        narrative_component = max(0.0, min(100.0, 100.0 - narrative_penalty))

        # 4. Executive Trend
        trend_component = 50.0
        # Sort preloaded trends by date and limit to 10
        sorted_trends = sorted(supporting_trends, key=lambda x: x.created_at, reverse=True)[:10]
        for t in sorted_trends:
            if t.severity in ["HIGH", "CRITICAL"]:
                if avg_sentiment < 0:
                    trend_component -= 15
                else:
                    trend_component += 15
        trend_component = max(0.0, min(100.0, trend_component))

        # 5. Executive Visibility
        # Count mentions in-memory
        total_mentions = len(doc_ids) # Or sum mention_counts if available. Let's use doc_ids count for consistency
        visibility_component = min(100.0, (total_mentions / 500.0) * 100.0)
        if visibility_component == 0: visibility_component = 50.0

        # A3: Dynamic Source Reliability
        source_reliability = 1.0
        if doc_urls:
            reliabilities = [self._calculate_source_reliability(url) for url in doc_urls]
            source_reliability = sum(reliabilities) / len(reliabilities)

        # Apply source reliability multiplier
        base_score = (
            sentiment_component * self.weights["sentiment"] +
            risk_component * self.weights["risk"] +
            narrative_component * self.weights["narrative"] +
            trend_component * self.weights["trend"] +
            visibility_component * self.weights["visibility"]
        )
        final_score = min(100.0, base_score * source_reliability)

        # Get previous score
        prev_reputation = db.query(ExecutiveReputationScore).filter(
            ExecutiveReputationScore.entity_id == exec_entity.id
        ).order_by(ExecutiveReputationScore.created_at.desc()).first()
        
        prev_score = prev_reputation.score if prev_reputation else None
        rep_trend = self._determine_trend(final_score, prev_score)

        # A7: Upstream Health Status Checking
        health_status = "COMPLETE"
        has_recent_risk = any(r.created_at >= one_day_ago for r in supporting_risks)
        has_recent_trend = any(t.created_at >= one_day_ago for t in sorted_trends)

        if not (has_recent_risk and has_recent_trend):
            health_status = "PARTIAL"

        # A6: Executive Confidence Score
        doc_confidence = min(len(doc_ids) / 10.0, 1.0)
        signal_completeness = (1.0 if has_recent_risk else 0.5) * 0.5 + (1.0 if has_recent_trend else 0.5) * 0.5
        confidence_score = round(doc_confidence * 0.6 + signal_completeness * 0.4, 4)

        # A4: Mathematical Lineage
        calculation_lineage = {
            "formula": "min(100.0, (0.35*Sentiment + 0.30*Risk + 0.15*Narrative + 0.10*Trend + 0.10*Visibility) * SourceReliability)",
            "component_scores": {
                "sentiment": round(sentiment_component, 2),
                "risk": round(risk_component, 2),
                "narrative": round(narrative_component, 2),
                "trend": round(trend_component, 2),
                "visibility": round(visibility_component, 2)
            },
            "component_weights": self.weights,
            "source_reliability": round(source_reliability, 4),
            "raw_values": {
                "avg_sentiment": round(avg_sentiment, 4),
                "total_mentions": total_mentions,
                "document_count": len(doc_ids)
            },
            "confidence_calculation": {
                "doc_confidence": round(doc_confidence, 4),
                "signal_completeness": round(signal_completeness, 4)
            },
            "decision_reason": f"Executive reputation calculated dynamically over 30-day window with health state: {health_status}."
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

        # Calculate data coverage
        data_coverage_val = 0.40
        try:
            from app.models.source import Source
            active_sources = db.query(Source).filter(Source.is_active == True).all()
            source_types = {s.source_type.lower() for s in active_sources}
            if "reddit" in source_types and ("google" in source_types or "youtube" in source_types or "news" in source_types):
                data_coverage_val = 0.75
            elif "reddit" in source_types:
                data_coverage_val = 0.58
            elif "rss" in source_types:
                data_coverage_val = 0.40
        except Exception:
            pass

        # R7: Duplicate protection using ON CONFLICT DO UPDATE on uq_exec_reputation_run
        stmt = insert(ExecutiveReputationScore).values(
            id=uuid.uuid4(),
            client_id=client_id,
            entity_id=exec_entity.id,
            executive_name=exec_entity.name,
            score=final_score,
            grade=self._determine_grade(final_score),
            sentiment_component=sentiment_component,
            risk_component=risk_component,
            narrative_component=narrative_component,
            trend_component=trend_component,
            visibility_component=visibility_component,
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
                "grade": self._determine_grade(final_score),
                "sentiment_component": sentiment_component,
                "risk_component": risk_component,
                "narrative_component": narrative_component,
                "trend_component": trend_component,
                "visibility_component": visibility_component,
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
