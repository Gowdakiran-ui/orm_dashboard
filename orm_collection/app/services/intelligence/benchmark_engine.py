import datetime
import time
import os
import uuid
import structlog
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.sentiment import DocumentSentiment
from app.models.risk import RiskEvent
from app.models.trends import TrendEvent
from app.models.narrative import Narrative
from app.models.executive_reputation import ExecutiveReputationScore
from app.models.reputation import ReputationScore
from app.models.competitor_benchmark import CompetitorBenchmark

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────
# BENCHMARK PROCESSING STATE MACHINE (R2)
# ─────────────────────────────────────────────────────────────
class BenchmarkStateMachine:
    PENDING = "BENCHMARK_PENDING"
    PROCESSING = "BENCHMARK_PROCESSING"
    COMPLETE = "BENCHMARK_COMPLETE"
    FAILED = "BENCHMARK_FAILED"
    RETRYING = "BENCHMARK_RETRYING"
    SKIPPED = "BENCHMARK_SKIPPED"

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
        from_state = client.benchmark_processing_status or BenchmarkStateMachine.PENDING
        if not BenchmarkStateMachine.is_valid_transition(from_state, to_state):
            logger.warning(
                "benchmark_invalid_state_transition",
                client_id=str(client.id),
                from_state=from_state,
                to_state=to_state
            )
            return False
        
        client.benchmark_processing_status = to_state
        if run_id is not None:
            client.benchmark_run_id = run_id
        if batch_id is not None:
            client.benchmark_batch_id = batch_id
        if failure_reason is not None:
            client.benchmark_failure_reason = str(failure_reason)[:4000]
        if retry_count is not None:
            client.benchmark_retry_count = retry_count
        if latency_ms is not None:
            client.benchmark_latency_ms = latency_ms
        if to_state == BenchmarkStateMachine.FAILED:
            client.benchmark_failed_at = datetime.datetime.now(datetime.timezone.utc)
        return True


class BenchmarkEngine:
    def calculate_competitor_benchmarks(
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
            processing_stage="BENCHMARK_CALCULATION"
        )
        log.info("benchmark_calculation_started")

        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            log.error("benchmark_client_not_found")
            raise ValueError(f"Client {client_id} not found")

        # A3: 30-day moving window configuration
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        lookback_date = now_utc - datetime.timedelta(days=30)

        # 1. Identify Client Brand Entity & Verified Competitor Entities
        client_entity = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "brand"
        ).first()
        
        if not client_entity:
            client_entity = db.query(Entity).filter(Entity.client_id == client_id).first()
            if not client_entity:
                log.info("benchmark_no_brand_entity_skipping")
                BenchmarkStateMachine.transition(db, client, BenchmarkStateMachine.SKIPPED, run_id=rid, batch_id=bid, failure_reason="No client entity found")
                db.commit()
                return
            
        # Only count verified competitors (entity_type == "competitor")
        # Do not use fallback to other entities - only real competitors count
        competitors = db.query(Entity).filter(
            Entity.client_id == client_id,
            Entity.entity_type == "competitor"
        ).all()
        
        # Benchmark requires Client + 1 or more REAL competitors
        if not competitors or len(competitors) < 1:
            log.info("benchmark_insufficient_competitors_skipped", count=len(competitors) if competitors else 0)
            BenchmarkStateMachine.transition(
                db, 
                client, 
                BenchmarkStateMachine.SKIPPED, 
                run_id=rid, 
                batch_id=bid,
                failure_reason="Insufficient verified competitors. Requires 1 or more verified competitors."
            )
            db.commit()
            return
            
        all_entities = [client_entity] + competitors
        all_entity_ids = [e.id for e in all_entities]
        
        # P3: Batch preloading of all mentions, sentiments, risks, and executive scores
        # 30-day mentions in bulk
        mentions_query = db.query(EntityMention.entity_id, func.sum(EntityMention.mention_count)).filter(
            EntityMention.entity_id.in_(all_entity_ids),
            EntityMention.created_at >= lookback_date
        ).group_by(EntityMention.entity_id).all()
        mentions_map = {eid: val for eid, val in mentions_query}

        # 30-day sentiment in bulk
        sentiment_query = db.query(EntityMention.entity_id, func.avg(DocumentSentiment.sentiment_score)).join(
            DocumentSentiment, DocumentSentiment.document_id == EntityMention.document_id
        ).filter(
            EntityMention.entity_id.in_(all_entity_ids),
            EntityMention.created_at >= lookback_date
        ).group_by(EntityMention.entity_id).all()
        sentiment_map = {eid: val for eid, val in sentiment_query}

        # 30-day risk in bulk
        risk_query = db.query(RiskEvent.entity_id, func.avg(RiskEvent.risk_score)).filter(
            RiskEvent.client_id == client_id,
            RiskEvent.entity_id.in_(all_entity_ids),
            RiskEvent.created_at >= lookback_date
        ).group_by(RiskEvent.entity_id).all()
        risk_map = {eid: val for eid, val in risk_query}

        # 30-day executive reputation in bulk
        exec_reps = db.query(ExecutiveReputationScore).filter(
            ExecutiveReputationScore.client_id == client_id,
            ExecutiveReputationScore.entity_id.in_(all_entity_ids),
            ExecutiveReputationScore.created_at >= lookback_date
        ).order_by(ExecutiveReputationScore.created_at.desc()).all()
        
        # Keep only the latest executive score per entity
        exec_rep_map = {}
        for er in exec_reps:
            if er.entity_id not in exec_rep_map:
                exec_rep_map[er.entity_id] = er.score

        # 30-day top narrative in bulk
        top_narr_record = db.query(Narrative).filter(
            Narrative.client_id == client_id,
            Narrative.updated_at >= lookback_date
        ).order_by(Narrative.confidence_score.desc(), Narrative.updated_at.desc()).first()
        top_narrative_text = top_narr_record.narrative_name if top_narr_record else None

        # Calculate Total Mentions for Share of Voice
        total_mentions = sum(mentions_map.values())
        
        # Compute Scores and SOV using in-memory maps (P3)
        benchmark_results = []
        for e in competitors:
            try:
                mentions = mentions_map.get(e.id, 0) or 0
                avg_sentiment = sentiment_map.get(e.id, 0.0) or 0.0
                avg_risk = risk_map.get(e.id, 0.0) or 0.0
                exec_score = exec_rep_map.get(e.id, None)

                # A8: Share of Voice Accuracy
                sov = (mentions / total_mentions * 100.0) if total_mentions > 0 else 0.0
                rep_score = ((avg_sentiment + 1.0) / 2.0) * 50.0 + (100.0 - avg_risk) * 0.5
                
                # A7: Health Status & A6: Confidence Calculation
                health_status = "COMPLETE"
                confidence_score = 1.0
                
                if exec_score is None:
                    health_status = "PARTIAL"
                    confidence_score -= 0.3
                    
                if top_narrative_text is None:
                    health_status = "PARTIAL"
                    confidence_score -= 0.1
                    
                if mentions < 5:
                    confidence_score -= 0.2
                    
                confidence_score = max(0.1, round(confidence_score, 2))
                
                benchmark_results.append({
                    "competitor_entity_id": e.id,
                    "reputation_score": rep_score,
                    "executive_reputation_score": exec_score or 0.0,
                    "sentiment_score": avg_sentiment,
                    "risk_score": avg_risk,
                    "visibility_score": float(mentions),
                    "share_of_voice": sov,
                    "top_narrative": top_narrative_text,
                    "health_status": health_status,
                    "confidence_score": confidence_score
                })
            except Exception as exc:
                log.error("benchmark_competitor_score_failed", competitor_id=str(e.id), error=str(exc))

        # A4: Dynamic Competitor Ranking
        all_reps = []
        for e in all_entities:
            mentions = mentions_map.get(e.id, 0) or 0
            avg_sentiment = sentiment_map.get(e.id, 0.0) or 0.0
            avg_risk = risk_map.get(e.id, 0.0) or 0.0
            exec_val = exec_rep_map.get(e.id, 50.0) or 50.0
            
            rep_score = ((avg_sentiment + 1.0)/2.0)*50 + (100.0 - avg_risk)*0.5
            sov_val = (mentions / total_mentions * 100.0) if total_mentions > 0 else 0.0
            
            composite_score = rep_score * 0.5 + exec_val * 0.3 + sov_val * 0.2
            all_reps.append((e.id, composite_score))
            
        all_reps.sort(key=lambda x: x[1], reverse=True)
        ranks = {ent_id: i+1 for i, (ent_id, _) in enumerate(all_reps)}
        
        # R5: Atomic Transactions - All inserts/updates are registered in the session
        # R6: Duplicate Protection using upsert (ON CONFLICT DO UPDATE)
        for res in benchmark_results:
            eid = res["competitor_entity_id"]
            rep_score = res["reputation_score"]
            latency_ms = (time.perf_counter() - t0) * 1000
            
            # A5: Explainability JSONB Lineage
            calculation_lineage = {
                "formula": "0.50*Reputation + 0.30*ExecutiveReputation + 0.20*ShareOfVoice",
                "component_scores": {
                    "reputation": round(rep_score, 2),
                    "executive_reputation": round(res["executive_reputation_score"], 2),
                    "share_of_voice": round(res["share_of_voice"], 2)
                },
                "decision_reason": f"Benchmark ranking computed dynamically over 30-day window with health state: {res['health_status']}."
            }
            
            evidence_metadata = {
                "supporting_executive_entity": str(eid)
            }
            
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

            stmt = insert(CompetitorBenchmark).values(
                id=uuid.uuid4(),
                client_id=client_id,
                competitor_entity_id=eid,
                reputation_score=rep_score,
                executive_reputation_score=res["executive_reputation_score"],
                sentiment_score=res["sentiment_score"],
                risk_score=res["risk_score"],
                visibility_score=res["visibility_score"],
                share_of_voice=res["share_of_voice"],
                top_narrative=res["top_narrative"],
                rank=ranks[eid],
                run_id=rid,
                batch_id=bid,
                worker_id=wid,
                latency_ms=latency_ms,
                retry_count=attempt,
                calculation_lineage=calculation_lineage,
                evidence_metadata=evidence_metadata,
                health_status=res["health_status"],
                confidence_score=res["confidence_score"],
                data_coverage=data_coverage_val
            ).on_conflict_do_update(
                constraint="uq_competitor_benchmark_run",
                set_={
                    "reputation_score": rep_score,
                    "executive_reputation_score": res["executive_reputation_score"],
                    "sentiment_score": res["sentiment_score"],
                    "risk_score": res["risk_score"],
                    "visibility_score": res["visibility_score"],
                    "share_of_voice": res["share_of_voice"],
                    "top_narrative": res["top_narrative"],
                    "rank": ranks[eid],
                    "batch_id": bid,
                    "worker_id": wid,
                    "latency_ms": latency_ms,
                    "retry_count": attempt,
                    "calculation_lineage": calculation_lineage,
                    "evidence_metadata": evidence_metadata,
                    "health_status": res["health_status"],
                    "confidence_score": res["confidence_score"],
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
        self.calculate_competitor_benchmarks(
            db,
            client_id,
            run_id=run_id,
            batch_id=batch_id,
            worker_id=worker_id,
            attempt=attempt
        )
