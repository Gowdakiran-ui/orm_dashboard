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
        elif to_state == BenchmarkStateMachine.COMPLETE:
            # B4: a successful transition must clear a stale failure reason
            # from a prior FAILED/RETRYING run — otherwise old failure text
            # persists indefinitely after BENCHMARK_COMPLETE.
            client.benchmark_failure_reason = None
        if retry_count is not None:
            client.benchmark_retry_count = retry_count
        if latency_ms is not None:
            client.benchmark_latency_ms = latency_ms
        if to_state == BenchmarkStateMachine.FAILED:
            client.benchmark_failed_at = datetime.datetime.now(datetime.timezone.utc)
        return True


class BenchmarkEngine:
    # A2.9 — score comparability.
    #
    # DECISION: option (a) — unify on ReputationEngine's weighted formula and its
    # dynamic-weight renormalization, applied identically to the client's brand
    # entity and to every competitor entity, so the values the UI plots on one
    # axis are actually the same measurement.
    #
    # The previous formula was `((sentiment+1)/2)*50 + (100-risk)*0.5`, a
    # two-component score, while the client's number came from
    # ReputationEngine's six-component weighted score. They were never
    # comparable, and the two-component form also produced exactly 75.0 for an
    # entity with no evidence at all (0 sentiment + 0 risk), which outranked
    # every real, evidenced client.
    #
    # FEASIBILITY, verified against the live schema before committing:
    #   sentiment  — per-entity  ✓ (EntityMention -> DocumentSentiment)
    #   risk       — per-entity  ✓ (RiskEvent.entity_id)
    #   trend      — per-entity  ✓ (TrendEvent.entity_id)
    #   source     — per-entity  ✓ (documents reachable via EntityMention)
    #   visibility — per-entity  ✓ (EntityMention.mention_count)
    #   narrative  — NOT per-entity  ✗  `narratives` has client_id only, no
    #                entity_id column. It therefore cannot be computed for a
    #                competitor at all.
    #
    # Narrative is consequently excluded for EVERY entity here, client included,
    # rather than being applied to one side only. ReputationEngine's own
    # dynamic-weight rule then renormalizes the remaining five weights, exactly
    # as it already does whenever a component is unavailable. The client's
    # comparable score is computed the same way and recorded in
    # calculation_lineage so the API/UI layer has a true apples-to-apples pair
    # to render (Phase B/C wiring).
    #
    # ReputationEngine.weights is imported rather than copied so there is one
    # source of truth for the weighting.
    COMPARABLE_COMPONENTS = ("sentiment", "risk", "trend", "source", "visibility")

    # A2.11 — single consistent default for a missing executive reputation
    # score. Previously the stored value used `exec_score or 0.0` while the
    # ranking composite read it back with a 50.0 default, so the two disagreed
    # by 50 points on every row. The ranking composite is gone (ranking now
    # uses the comparable score), and 0.0 matches both the NOT NULL column
    # default and every one of the 351 rows already stored.
    MISSING_EXECUTIVE_SCORE = 0.0

    # Mirrors ReputationEngine's coverage rule: below this share of the total
    # weight mass, there is not enough signal to state a score at all.
    MIN_ACTIVE_WEIGHT = 0.20

    def _score_from_components(self, components: Dict[str, Optional[float]], weights: Dict[str, float]):
        """
        ReputationEngine's dynamic weight normalization, reused verbatim in
        behaviour: components that could not be computed are dropped and the
        remaining weights are renormalized. Returns (score, active_weight).
        `score` is None when coverage is below MIN_ACTIVE_WEIGHT — that is the
        "no plausible-looking number without evidence" case (A2.10).
        """
        active = {k: v for k, v in components.items() if v is not None}
        total_weight = sum(weights[k] for k in active)
        if total_weight < self.MIN_ACTIVE_WEIGHT:
            return None, total_weight
        weighted_sum = sum(v * weights[k] for k, v in active.items())
        score = max(0.0, min(100.0, weighted_sum / total_weight))
        return score, total_weight

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

        # 30-day trend events per entity (A2.9 — trend component).
        # Same shape as ReputationEngine's trend rule, but scoped by entity_id
        # instead of client-wide, which trend_events supports.
        trend_rows = db.query(TrendEvent).filter(
            TrendEvent.client_id == client_id,
            TrendEvent.entity_id.in_(all_entity_ids),
            TrendEvent.created_at >= lookback_date
        ).order_by(TrendEvent.created_at.desc()).all()
        trends_by_entity: Dict[Any, List[Any]] = {}
        for tev in trend_rows:
            bucket = trends_by_entity.setdefault(tev.entity_id, [])
            if len(bucket) < 10:  # ReputationEngine uses the 10 most recent
                bucket.append(tev)

        # 30-day source reliability per entity (A2.9 — source component).
        # Reuses SourceCategory.base_reliability_score / SourceHealth.penalty,
        # the same inputs ReputationEngine uses, restricted to the documents
        # that actually mention each entity.
        from app.models.document import Document
        from app.models.source import Source, SourceCategory, SourceHealth

        reliability_by_entity: Dict[Any, List[float]] = {}
        try:
            source_rows = db.query(
                EntityMention.entity_id,
                SourceCategory.base_reliability_score,
                SourceHealth.reliability_penalty
            ).select_from(EntityMention).join(
                Document, Document.id == EntityMention.document_id
            ).join(
                Source, Document.source_id == Source.id
            ).join(
                SourceCategory, Source.category_id == SourceCategory.id
            ).outerjoin(
                SourceHealth, Source.id == SourceHealth.source_id
            ).filter(
                EntityMention.entity_id.in_(all_entity_ids),
                EntityMention.created_at >= lookback_date
            ).all()
            for eid, base_score, penalty in source_rows:
                score = float(base_score or 1.00)
                pen = float(penalty or 0.0)
                reliability_by_entity.setdefault(eid, []).append(
                    max(0.0, min(100.0, (score - pen) * 100))
                )
        except Exception as exc:
            log.warning("benchmark_source_component_unavailable", error=str(exc))

        # 30-day top narrative in bulk.
        # NOTE: client-scoped, not entity-scoped — `narratives` has no
        # entity_id column. Retained as descriptive context on the row; it is
        # deliberately NOT a scoring component (see COMPARABLE_COMPONENTS).
        top_narr_record = db.query(Narrative).filter(
            Narrative.client_id == client_id,
            Narrative.updated_at >= lookback_date
        ).order_by(Narrative.confidence_score.desc(), Narrative.updated_at.desc()).first()
        top_narrative_text = top_narr_record.narrative_name if top_narr_record else None

        # Calculate Total Mentions for Share of Voice
        total_mentions = sum(mentions_map.values())

        # Single source of truth for the component weights.
        from app.services.intelligence.reputation_engine import ReputationEngine
        weights = ReputationEngine().weights

        def _components_for(entity_id):
            """Per-entity component scores on ReputationEngine's 0-100 scale.
            None means 'not computable', which the weight normalization drops."""
            mentions = mentions_map.get(entity_id, 0) or 0
            avg_sent = sentiment_map.get(entity_id, None)
            avg_rsk = risk_map.get(entity_id, None)

            sentiment_component = ((float(avg_sent) + 1.0) / 2.0) * 100.0 if avg_sent is not None else None
            risk_component = 100.0 - float(avg_rsk) if avg_rsk is not None else None

            trend_component = None
            entity_trends = trends_by_entity.get(entity_id)
            if entity_trends:
                trend_val = 50.0
                for tev in entity_trends:
                    if tev.severity in ("HIGH", "CRITICAL"):
                        if tev.trend_type == "Sentiment":
                            trend_val -= 20
                        elif (float(avg_sent) if avg_sent is not None else 0.0) < 0:
                            trend_val -= 15
                        else:
                            trend_val += 15
                trend_component = max(0.0, min(100.0, trend_val))

            reliabilities = reliability_by_entity.get(entity_id)
            source_component = (sum(reliabilities) / len(reliabilities)) if reliabilities else None

            visibility_component = (
                min(100.0, (mentions / (mentions + 5000.0)) * 100.0) if mentions > 0 else None
            )

            return {
                "sentiment": sentiment_component,
                "risk": risk_component,
                "trend": trend_component,
                "source": source_component,
                "visibility": visibility_component,
            }

        # Comparable score for the client's own brand entity, computed by the
        # identical path so the axis is self-consistent (A2.9).
        client_components = _components_for(client_entity.id)
        client_score, client_active_weight = self._score_from_components(client_components, weights)

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

                components = _components_for(e.id)
                rep_score, active_weight = self._score_from_components(components, weights)

                # A2.10 — no evidence must not yield a plausible-looking number.
                # The old formula returned exactly 75.0 here. Now the row is
                # still written (so it supersedes any stale high-scoring row for
                # the same competitor) but is flagged distinctly and left out of
                # the ranking entirely.
                has_evidence = rep_score is not None

                # A6: Confidence — mirrors ReputationEngine's own definition
                # (document volume 40% + signal completeness 60%) instead of the
                # previous ad-hoc deductions, so the two engines report
                # confidence on the same basis.
                doc_confidence = min(mentions / 50.0, 1.0)
                confidence_score = round(doc_confidence * 0.4 + active_weight * 0.6, 4)

                # A7: Health status
                if not has_evidence:
                    health_status = "INSUFFICIENT_EVIDENCE"
                    confidence_score = 0.0
                elif active_weight >= sum(weights[k] for k in self.COMPARABLE_COMPONENTS) - 1e-9:
                    health_status = "COMPLETE"
                else:
                    health_status = "PARTIAL"

                benchmark_results.append({
                    "competitor_entity_id": e.id,
                    "reputation_score": rep_score if has_evidence else 0.0,
                    "has_evidence": has_evidence,
                    "components": components,
                    "active_weight": active_weight,
                    "executive_reputation_score": exec_score if exec_score is not None else self.MISSING_EXECUTIVE_SCORE,
                    "sentiment_score": avg_sentiment,
                    "risk_score": avg_risk,
                    "visibility_score": float(mentions),
                    "share_of_voice": sov,
                    "top_narrative": top_narrative_text,
                    "health_status": health_status,
                    "confidence_score": confidence_score,
                    "doc_confidence": doc_confidence,
                })
            except Exception as exc:
                log.error("benchmark_competitor_score_failed", competitor_id=str(e.id), error=str(exc))

        # A4: Dynamic ranking — over the client plus every competitor, by the
        # one comparable score. The previous separate composite
        # (rep*0.5 + exec*0.3 + sov*0.2) is removed: it was a third, different
        # ranking that contradicted what the UI displayed (live Tesla was rank
        # #1 by the composite and last by score) and it was the only consumer of
        # the inconsistent 50.0 executive default.
        #
        # Entities with no evidence are NOT ranked. rank stays 0, which the
        # column already defaults to, and reads as "unranked".
        scored_entities = []
        if client_score is not None:
            scored_entities.append((client_entity.id, client_score))
        for res in benchmark_results:
            if res["has_evidence"]:
                scored_entities.append((res["competitor_entity_id"], res["reputation_score"]))

        # Deterministic ordering: score desc, then entity id, so equal scores
        # never reshuffle between runs.
        scored_entities.sort(key=lambda x: (-x[1], str(x[0])))
        ranks = {ent_id: i + 1 for i, (ent_id, _) in enumerate(scored_entities)}

        log.info(
            "benchmark_scores_computed",
            client_comparable_score=round(client_score, 2) if client_score is not None else None,
            competitors_scored=len(scored_entities) - (1 if client_score is not None else 0),
            competitors_unranked=sum(1 for r in benchmark_results if not r["has_evidence"]),
        )

        # R5: Atomic Transactions - All inserts/updates are registered in the session
        # R6: Duplicate Protection using upsert (ON CONFLICT DO UPDATE)
        for res in benchmark_results:
            eid = res["competitor_entity_id"]
            rep_score = res["reputation_score"]
            # 0 = unranked (the column's own default) for entities with no
            # evidence, which are deliberately absent from `ranks`.
            entity_rank = ranks.get(eid, 0)
            latency_ms = (time.perf_counter() - t0) * 1000
            
            # A2.12 — Explainability lineage that actually describes the value
            # it is attached to. The previous record documented a composite
            # ("0.50*Reputation + 0.30*ExecutiveReputation + 0.20*ShareOfVoice")
            # that matched neither reputation_score nor the ranking it was
            # supposed to explain, and reported executive_reputation as 0.0 while
            # the ranking used 50.0.
            calculation_lineage = {
                "formula": "Weighted Sum of Available Components / Total Available Weights",
                "scored_value": "reputation_score",
                "component_scores": {
                    k: (round(v, 2) if v is not None else None)
                    for k, v in res["components"].items()
                },
                "component_weights": {k: weights[k] for k in self.COMPARABLE_COMPONENTS},
                "active_weight_sum": round(res["active_weight"], 4),
                "excluded_components": {
                    "narrative": "not computable per entity — narratives table has no entity_id; "
                                 "excluded for the client entity too so both sides are comparable"
                },
                # Same formula, same window, same weights, computed for the
                # client's brand entity — the apples-to-apples counterpart the
                # UI needs. Recorded here rather than in a new column: no
                # migration, and this row is already the explainability record.
                "client_comparable_score": round(client_score, 2) if client_score is not None else None,
                "client_active_weight_sum": round(client_active_weight, 4),
                "decision_reason": (
                    f"Insufficient evidence: active weight {res['active_weight']:.2f} < "
                    f"{self.MIN_ACTIVE_WEIGHT:.2f}; no score stated and entity left unranked."
                    if not res["has_evidence"] else
                    f"Comparable reputation computed over a 30-day window from "
                    f"{sum(1 for v in res['components'].values() if v is not None)} of "
                    f"{len(self.COMPARABLE_COMPONENTS)} components; health state: {res['health_status']}."
                ),
            }

            evidence_metadata = {
                "competitor_entity_id": str(eid),
                "client_entity_id": str(client_entity.id),
                "mentions_30d": res["visibility_score"],
                "total_mentions_30d": total_mentions,
            }

            # A2.13 — real per-competitor coverage instead of the fixed
            # 0.40/0.58/0.75 ladder, which was derived from which source *types*
            # were active platform-wide and was therefore identical for every
            # competitor of every client (live: every one of 351 rows was 0.40).
            # Mirrors ReputationEngine, which likewise sets data_coverage to its
            # confidence score, so the two engines report coverage on one basis.
            data_coverage_val = res["confidence_score"]

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
                rank=entity_rank,
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
                    "rank": entity_rank,
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
