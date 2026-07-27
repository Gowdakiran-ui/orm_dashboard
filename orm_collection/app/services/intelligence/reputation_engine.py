import datetime
import time
import os
import uuid
import math
import structlog
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.models.document import Document
from app.models.entity import EntityMention, Entity
from app.models.sentiment import DocumentSentiment
from app.models.risk import RiskEvent
from app.models.trends import TrendEvent
from app.models.narrative import Narrative
from app.models.reputation import ReputationScore
from app.models.client import Client
from app.models.alert import Alert

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────
# REPUTATION PROCESSING STATE MACHINE (R2)
# ─────────────────────────────────────────────────────────────
class ReputationStateMachine:
    PENDING = "REPUTATION_PENDING"
    PROCESSING = "REPUTATION_PROCESSING"
    COMPLETE = "REPUTATION_COMPLETE"
    FAILED = "REPUTATION_FAILED"
    RETRYING = "REPUTATION_RETRYING"
    SKIPPED = "REPUTATION_SKIPPED"

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
        from_state = client.reputation_processing_status or ReputationStateMachine.PENDING
        if not ReputationStateMachine.is_valid_transition(from_state, to_state):
            logger.warning(
                "reputation_invalid_state_transition",
                client_id=str(client.id),
                from_state=from_state,
                to_state=to_state
            )
            return False
        
        client.reputation_processing_status = to_state
        if run_id is not None:
            client.reputation_run_id = run_id
        if batch_id is not None:
            client.reputation_batch_id = batch_id
        if failure_reason is not None:
            client.reputation_failure_reason = str(failure_reason)[:4000]
        if retry_count is not None:
            client.reputation_retry_count = retry_count
        if latency_ms is not None:
            client.reputation_latency_ms = latency_ms
        if to_state == ReputationStateMachine.FAILED:
            client.reputation_failed_at = datetime.datetime.now(datetime.timezone.utc)
        return True


class ReputationEngine:
    def __init__(self):
        self.weights = {
            "sentiment": 0.30,
            "risk": 0.30,
            "narrative": 0.15,
            "trend": 0.10,
            "source": 0.10,
            "visibility": 0.05
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

    # Removed hardcoded _calculate_source_reliability

    def calculate_reputation_score(
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
            processing_stage="REPUTATION_CALCULATION"
        )
        log.info("reputation_calculation_started")

        # A2: Configure 30-day moving window
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        lookback_date = now_utc - datetime.timedelta(days=30)

        # P3: Batch preloading of all client entities
        entities = db.query(Entity).filter(Entity.client_id == client_id).all()
        entity_ids = [e.id for e in entities]

        doc_ids = []
        doc_urls = []
        total_mentions = 0
        
        if entity_ids:
            # P3: Batch preloading of all mentions in the 30-day window
            mentions = db.query(EntityMention).filter(
                EntityMention.entity_id.in_(entity_ids),
                EntityMention.created_at >= lookback_date
            ).all()
            doc_ids = list(set(m.document_id for m in mentions))
            total_mentions = sum(m.mention_count for m in mentions)
            
            if doc_ids:
                # P3: Batch preloading of document URLs
                documents = db.query(Document.id, Document.url).filter(Document.id.in_(doc_ids)).all()
                doc_urls = [d[1] for d in documents if d[1]]

        # 1. Sentiment Component (R5 Isolated)
        sentiment_component = None
        avg_sentiment = None
        if doc_ids:
            try:
                avg_sentiment_val = db.query(func.avg(DocumentSentiment.sentiment_score)).filter(
                    DocumentSentiment.document_id.in_(doc_ids)
                ).scalar()
                if avg_sentiment_val is not None:
                    avg_sentiment = float(avg_sentiment_val)
                    sentiment_component = ((avg_sentiment + 1.0) / 2.0) * 100.0
            except Exception as e:
                log.warning("reputation_sentiment_calculation_failed", error=str(e))

        # 2. Risk Component (R5 Isolated)
        risk_component = None
        supporting_risks = []
        try:
            supporting_risks = db.query(RiskEvent).filter(
                RiskEvent.client_id == client_id,
                RiskEvent.created_at >= lookback_date
            ).all()
            if supporting_risks:
                avg_risk = sum(r.risk_score for r in supporting_risks) / len(supporting_risks)
                risk_component = 100.0 - avg_risk
        except Exception as e:
            log.warning("reputation_risk_calculation_failed", error=str(e))

        # 3. Narratives Component (R5 Isolated)
        narrative_component = None
        supporting_narratives = []
        try:
            supporting_narratives = db.query(Narrative).filter(
                Narrative.client_id == client_id,
                Narrative.updated_at >= lookback_date
            ).all()
            if supporting_narratives:
                narrative_penalty = 0
                for n in supporting_narratives:
                    if n.sentiment_score < 0 and n.status in ["GROWING", "PEAK"]:
                        narrative_penalty += 20
                    elif n.sentiment_score > 0 and n.status in ["GROWING", "PEAK"]:
                        narrative_penalty -= 10
                narrative_component = max(0.0, min(100.0, 100.0 - narrative_penalty))
        except Exception as e:
            log.warning("reputation_narrative_calculation_failed", error=str(e))

        # 4. Trend Component (R5 Isolated)
        trend_component = None
        supporting_trends = []
        try:
            supporting_trends = db.query(TrendEvent).filter(
                TrendEvent.client_id == client_id,
                TrendEvent.created_at >= lookback_date
            ).order_by(TrendEvent.created_at.desc()).limit(10).all()
            
            if supporting_trends:
                trend_val = 50.0
                for t in supporting_trends:
                    if t.severity in ["HIGH", "CRITICAL"]:
                        if t.trend_type == "Sentiment":
                            trend_val -= 20
                        else:
                            # fallback to 0.0 if avg_sentiment is None
                            if (avg_sentiment or 0.0) < 0:
                                trend_val -= 15
                            else:
                                trend_val += 15
                trend_component = max(0.0, min(100.0, trend_val))
        except Exception as e:
            log.warning("reputation_trend_calculation_failed", error=str(e))

        # 5. Source Quality Component (Dynamic Source Reliability)
        source_component = None
        if doc_ids:
            try:
                from app.models.source import Source, SourceCategory, SourceHealth
                sources_data = db.query(SourceCategory.base_reliability_score, SourceHealth.reliability_penalty).select_from(Document).join(
                    Source, Document.source_id == Source.id
                ).join(
                    SourceCategory, Source.category_id == SourceCategory.id
                ).outerjoin(
                    SourceHealth, Source.id == SourceHealth.source_id
                ).filter(Document.id.in_(doc_ids)).all()
                
                if sources_data:
                    reliabilities = []
                    for base_score, penalty in sources_data:
                        score = float(base_score or 1.00)
                        p = float(penalty or 0.0)
                        rel_score = max(0.0, min(100.0, (score - p) * 100))
                        reliabilities.append(rel_score)
                    if reliabilities:
                        source_component = sum(reliabilities) / len(reliabilities)
            except Exception as e:
                log.warning("reputation_source_calculation_failed", error=str(e))

        # 6. Visibility Component (Logistic Normalization)
        visibility_component = None
        if total_mentions > 0:
            visibility_component = min(100.0, (total_mentions / (total_mentions + 5000.0)) * 100.0)

        # Dynamic Weight Normalization
        active_weights = {
            "sentiment": sentiment_component,
            "risk": risk_component,
            "narrative": narrative_component,
            "trend": trend_component,
            "source": source_component,
            "visibility": visibility_component
        }
        
        total_weight = sum(self.weights[k] for k, v in active_weights.items() if v is not None)
        
        # Coverage Validation Threshold
        if total_weight < 0.20:
            final_score = None
        else:
            weighted_sum = sum(v * self.weights[k] for k, v in active_weights.items() if v is not None)
            final_score = weighted_sum / total_weight
            final_score = max(0.0, min(100.0, final_score))

        # Get previous score for trend
        prev_score = None
        try:
            prev_reputation = db.query(ReputationScore).filter(
                ReputationScore.client_id == client_id
            ).order_by(ReputationScore.created_at.desc()).first()
            prev_score = prev_reputation.score if prev_reputation else None
        except Exception as e:
            log.warning("reputation_previous_score_fetch_failed", error=str(e))

        rep_trend = self._determine_trend(final_score, prev_score)

        # A9: Upstream Health Status Checking
        health_status = "COMPLETE"
        one_day_ago = now_utc - datetime.timedelta(days=1)
        
        has_recent_risk = db.query(RiskEvent).filter(RiskEvent.client_id == client_id, RiskEvent.created_at >= one_day_ago).limit(1).first() is not None
        has_recent_trend = db.query(TrendEvent).filter(TrendEvent.client_id == client_id, TrendEvent.created_at >= one_day_ago).limit(1).first() is not None
        has_recent_narrative = db.query(Narrative).filter(Narrative.client_id == client_id, Narrative.updated_at >= one_day_ago).limit(1).first() is not None

        if not (has_recent_risk and has_recent_trend and has_recent_narrative):
            health_status = "PARTIAL"

        # A8: Reputation Confidence Calculation
        doc_confidence = min(len(doc_ids) / 50.0, 1.0) # Scale it up to 50 docs for full confidence
        signal_completeness = total_weight
        confidence_score = round(doc_confidence * 0.4 + signal_completeness * 0.6, 4)
        
        # Override coverage to confidence score to represent data quality
        data_coverage_val = confidence_score

        # A4: Mathematical Explainability Lineage
        calculation_lineage = {
            "formula": "Weighted Sum of Available Components / Total Available Weights",
            "component_scores": {
                "sentiment": round(sentiment_component, 2) if sentiment_component is not None else None,
                "risk": round(risk_component, 2) if risk_component is not None else None,
                "narrative": round(narrative_component, 2) if narrative_component is not None else None,
                "trend": round(trend_component, 2) if trend_component is not None else None,
                "source": round(source_component, 2) if source_component is not None else None,
                "visibility": round(visibility_component, 2) if visibility_component is not None else None
            },
            "component_weights": self.weights,
            "active_weight_sum": round(total_weight, 4),
            "raw_values": {
                "avg_sentiment": round(avg_sentiment, 4) if avg_sentiment is not None else None,
                "total_mentions": total_mentions,
                "document_count": len(doc_ids)
            },
            "confidence_calculation": {
                "doc_confidence": round(doc_confidence, 4),
                "signal_completeness": round(signal_completeness, 4)
            },
            "decision_reason": f"Reputation dynamically weighted over 30-day window with active total_weight={round(total_weight, 2)}."
        }

        # A5: Evidence Metadata (UUIDs of contributing signals)
        supporting_alerts = db.query(Alert).filter(
            Alert.client_id == client_id,
            Alert.created_at >= lookback_date
        ).all()

        evidence_metadata = {
            "supporting_documents": [str(did) for did in doc_ids],
            "supporting_risks": [str(r.id) for r in supporting_risks],
            "supporting_trends": [str(t.id) for t in supporting_trends],
            "supporting_alerts": [str(a.id) for a in supporting_alerts],
            "supporting_narratives": [str(n.id) for n in supporting_narratives]
        }

        latency_ms = (time.perf_counter() - t0) * 1000

        # Calculate data coverage block removed (using data_coverage_val = confidence_score instead)

        # R6: Duplicate Protection using upsert on unique constraint
        savepoint = db.begin_nested()
        try:
            stmt = insert(ReputationScore).values(
                id=uuid.uuid4(),
                client_id=client_id,
                score=final_score,
                grade=self._determine_grade(final_score),
                sentiment_component=sentiment_component,
                risk_component=risk_component,
                narrative_component=narrative_component,
                trend_component=trend_component,
                source_component=source_component,
                visibility_component=visibility_component,
                confidence_score=confidence_score,
                reputation_trend=rep_trend,
                run_id=rid,
                batch_id=bid,
                worker_id=wid,
                latency_ms=latency_ms,
                retry_count=attempt,
                evidence_metadata=evidence_metadata,
                calculation_lineage=calculation_lineage,
                health_status=health_status,
                data_coverage=data_coverage_val
            ).on_conflict_do_update(
                constraint="uq_client_reputation_run",
                set_={
                    "score": final_score,
                    "grade": self._determine_grade(final_score),
                    "sentiment_component": sentiment_component,
                    "risk_component": risk_component,
                    "narrative_component": narrative_component,
                    "trend_component": trend_component,
                    "source_component": source_component,
                    "visibility_component": visibility_component,
                    "confidence_score": confidence_score,
                    "reputation_trend": rep_trend,
                    "batch_id": bid,
                    "worker_id": wid,
                    "latency_ms": latency_ms,
                    "retry_count": attempt,
                    "evidence_metadata": evidence_metadata,
                    "calculation_lineage": calculation_lineage,
                    "health_status": health_status,
                    "data_coverage": data_coverage_val
                }
            )
            db.execute(stmt)
            savepoint.commit()
            log.info("reputation_calculation_complete", latency_ms=round(latency_ms, 2))
        except Exception as e:
            savepoint.rollback()
            log.error("reputation_savepoint_failed", error=str(e))
            raise e

    def process_client(
        self,
        db: Session,
        client_id: str,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        attempt: int = 0
    ):
        self.calculate_reputation_score(
            db,
            client_id,
            run_id=run_id,
            batch_id=batch_id,
            worker_id=worker_id,
            attempt=attempt
        )
