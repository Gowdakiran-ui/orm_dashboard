import time
import json
import uuid
import os
import datetime
import structlog
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

# Models
from app.models.client import Client
from app.models.entity import Entity, EntityMention
from app.models.reputation import ReputationScore
from app.models.executive_reputation import ExecutiveReputationScore
from app.models.competitor_benchmark import CompetitorBenchmark
from app.models.risk import RiskEvent
from app.models.alert import Alert
from app.models.narrative import Narrative
from app.models.trends import TrendEvent
from app.models.topic import Topic, DocumentTopic
from app.models.sentiment import DocumentSentiment
from app.models.document import Document
from app.models.source import Source

# Serializers, Cache, Validators
from app.services.ai.serializers import (
    serialize_client, serialize_entity, serialize_reputation,
    serialize_executive_reputation, serialize_benchmark, serialize_risk_event,
    serialize_alert, serialize_narrative, serialize_trend_event, serialize_document
)
from app.services.ai.validators import validate_context_payload
from app.services.ai.context_cache import context_cache

logger = structlog.get_logger()

class ContextBuilder:
    def __init__(self, use_cache: bool = True, max_tokens: int = 4096):
        self.use_cache = use_cache
        self.max_tokens = max_tokens
        self.context_version = "1.1.0"
        self.pipeline_version = "10.4.1"

    def estimate_tokens(self, text: str) -> int:
        """Heuristic token count (approx. 4 characters per token)."""
        return len(text) // 4

    def count_actual_tokens(self, text: str) -> int:
        """Accurate tokenizer matching the configured model with fallback."""
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            try:
                from transformers import GPT2TokenizerFast
                tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")
                return len(tokenizer.encode(text))
            except Exception:
                return len(text) // 4

    def calculate_data_coverage(
        self,
        db: Session,
        client_id: str,
        active_entities: List[Entity],
        reputation: Optional[ReputationScore],
        executives: List[ExecutiveReputationScore],
        benchmarks: List[CompetitorBenchmark],
        risks: List[RiskEvent],
        alerts: List[Alert],
        narratives: List[Narrative],
        trends: List[TrendEvent]
    ) -> Dict[str, Any]:
        """
        A3: Data Coverage Score (0-100%).
        Measures the availability of data sources and presence of intelligence signals.
        """
        enabled_sources = []
        missing_sources = []
        
        try:
            # Check active sources in the system
            active_srcs = db.query(Source).filter(Source.is_active == True).all()
            source_types = {s.source_type.lower() for s in active_srcs}
        except Exception:
            source_types = {"rss"}  # Default fallback

        for src in ["rss", "google", "reddit", "youtube"]:
            if src in source_types:
                enabled_sources.append(src)
            else:
                missing_sources.append(src)

        # Calculate coverage score
        # 40% based on enabled sources
        source_score = (len(enabled_sources) / 4.0) * 40.0
        
        # 60% based on populated data tables
        data_signals = {
            "reputation": reputation is not None,
            "executives": len(executives) > 0,
            "benchmarks": len(benchmarks) > 0,
            "risks": len(risks) > 0,
            "alerts": len(alerts) > 0,
            "narratives": len(narratives) > 0,
            "trends": len(trends) > 0
        }
        
        present_signals = [k for k, v in data_signals.items() if v]
        missing_signals = [k for k, v in data_signals.items() if not v]
        
        signal_score = (len(present_signals) / 7.0) * 60.0
        coverage_score = round(source_score + signal_score, 2)

        reason = f"Data coverage is {coverage_score}% based on {len(enabled_sources)} enabled sources and {len(present_signals)}/7 active intelligence signals."
        if missing_signals:
            reason += f" Missing signals: {', '.join(missing_signals)}."
        if missing_sources:
            reason += f" Missing sources: {', '.join(missing_sources)}."

        return {
            "coverage_score": coverage_score,
            "coverage_reason": reason,
            "missing_sources": missing_sources + missing_signals,
            "enabled_sources": enabled_sources + present_signals
        }

    def evaluate_context_quality(self, coverage_score: float, documents: List[Document]) -> str:
        """
        A4: Context Quality Score (HIGH, MEDIUM, LOW).
        Based on data coverage and freshness of documents.
        """
        if not documents:
            return "LOW"
            
        # Check freshness (if any document is from last 24 hours)
        now = datetime.datetime.now(datetime.timezone.utc)
        has_fresh_docs = False
        for d in documents:
            pub_date = d.published_at or d.collected_at
            if pub_date:
                # Handle offset-naive vs offset-aware datetime comparison
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=datetime.timezone.utc)
                if (now - pub_date).days <= 2:
                    has_fresh_docs = True
                    break

        if coverage_score >= 75.0 and has_fresh_docs:
            return "HIGH"
        elif coverage_score >= 45.0:
            return "MEDIUM"
        else:
            return "LOW"

    def build_compact(
        self,
        db: Session,
        client_id: str,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """A5: Compact Context (Chat, Advisor)"""
        return self.build_context(
            db, client_id, start_date, end_date,
            max_docs=5, max_alerts=3, max_risks=3, max_narratives=3,
            run_id=run_id, batch_id=batch_id, mode="compact"
        )

    def build_standard(
        self,
        db: Session,
        client_id: str,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """A5: Standard Context (Executive Brief)"""
        return self.build_context(
            db, client_id, start_date, end_date,
            max_docs=10, max_alerts=5, max_risks=5, max_narratives=5,
            run_id=run_id, batch_id=batch_id, mode="standard"
        )

    def build_full(
        self,
        db: Session,
        client_id: str,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """A5: Full Context (Crisis Planner)"""
        return self.build_context(
            db, client_id, start_date, end_date,
            max_docs=20, max_alerts=10, max_risks=10, max_narratives=10,
            run_id=run_id, batch_id=batch_id, mode="full"
        )

    def build_context(
        self,
        db: Session,
        client_id: str,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        max_docs: int = 20,
        max_alerts: int = 10,
        max_risks: int = 10,
        max_narratives: int = 10,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        mode: str = "standard"
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        rid = run_id or uuid.uuid4().hex
        bid = batch_id or uuid.uuid4().hex[:12]
        wid = str(os.getpid())

        log = logger.bind(
            run_id=rid,
            batch_id=bid,
            worker_id=wid,
            client_id=client_id,
            mode=mode,
            task="build_context"
        )
        log.info("context_build_started")

        # 1. Check Cache
        if self.use_cache:
            cached_data = context_cache.get(client_id)
            if cached_data and cached_data.get("metadata", {}).get("stats", {}).get("documents_loaded", 0) >= max_docs:
                log.info("context_build_cache_hit", latency_ms=round((time.perf_counter() - t0)*1000, 2))
                return cached_data

        # Set default 30-day window if not provided
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if not start_date:
            start_date = now_utc - datetime.timedelta(days=30)
        if not end_date:
            end_date = now_utc

        start_naive = start_date.replace(tzinfo=None)
        end_naive = end_date.replace(tzinfo=None)

        # 2. Query Database (READ ONLY)
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise ValueError(f"Client {client_id} not found.")

        entities = db.query(Entity).filter(Entity.client_id == client_id).all()
        entity_ids = [e.id for e in entities]
        entity_names = {e.id: e.name for e in entities}

        reputation = db.query(ReputationScore).filter(
            ReputationScore.client_id == client_id,
            ReputationScore.created_at >= start_naive,
            ReputationScore.created_at <= end_naive
        ).order_by(ReputationScore.created_at.desc()).first()

        exec_reps = db.query(ExecutiveReputationScore).filter(
            ExecutiveReputationScore.client_id == client_id,
            ExecutiveReputationScore.created_at >= start_naive,
            ExecutiveReputationScore.created_at <= end_naive
        ).order_by(ExecutiveReputationScore.created_at.desc()).all()
        
        latest_execs = {}
        for er in exec_reps:
            if er.entity_id not in latest_execs:
                latest_execs[er.entity_id] = er

        benchmarks = db.query(CompetitorBenchmark).filter(
            CompetitorBenchmark.client_id == client_id,
            CompetitorBenchmark.created_at >= start_naive,
            CompetitorBenchmark.created_at <= end_naive
        ).order_by(CompetitorBenchmark.created_at.desc()).all()
        
        latest_benchmarks = {}
        for bm in benchmarks:
            if bm.competitor_entity_id not in latest_benchmarks:
                latest_benchmarks[bm.competitor_entity_id] = bm

        risks = db.query(RiskEvent).filter(
            RiskEvent.client_id == client_id,
            RiskEvent.created_at >= start_naive,
            RiskEvent.created_at <= end_naive
        ).order_by(RiskEvent.risk_score.desc()).all()

        alerts = db.query(Alert).filter(
            Alert.client_id == client_id,
            Alert.created_at >= start_naive,
            Alert.created_at <= end_naive
        ).order_by(Alert.created_at.desc()).all()

        narratives = db.query(Narrative).filter(
            Narrative.client_id == client_id,
            Narrative.updated_at >= start_naive,
            Narrative.updated_at <= end_naive
        ).order_by(Narrative.risk_score.desc(), Narrative.mention_count.desc()).all()

        trends = db.query(TrendEvent).filter(
            TrendEvent.client_id == client_id,
            TrendEvent.created_at >= start_naive,
            TrendEvent.created_at <= end_naive
        ).order_by(TrendEvent.percentage_change.desc()).all()

        doc_ids = []
        if entity_ids:
            mentions = db.query(EntityMention.document_id).filter(
                EntityMention.entity_id.in_(entity_ids),
                EntityMention.created_at >= start_naive,
                EntityMention.created_at <= end_naive
            ).all()
            doc_ids = list(set(m.document_id for m in mentions))

        documents = []
        sentiment_map = {}
        topic_map = {}
        if doc_ids:
            documents = db.query(Document).filter(Document.id.in_(doc_ids)).all()
            sents = db.query(DocumentSentiment.document_id, DocumentSentiment.sentiment_score).filter(
                DocumentSentiment.document_id.in_(doc_ids)
            ).all()
            sentiment_map = {s[0]: s[1] for s in sents}
            topics = db.query(DocumentTopic.document_id, Topic.name).join(
                Topic, Topic.id == DocumentTopic.topic_id
            ).filter(DocumentTopic.document_id.in_(doc_ids)).all()
            topic_map = {t[0]: t[1] for t in topics}

        # Save stats before compression
        raw_docs_count = len(documents)
        raw_risks_count = len(risks)
        raw_alerts_count = len(alerts)
        raw_narratives_count = len(narratives)
        raw_trends_count = len(trends)

        # 3. Compression, Deduplication, and Sorting (Token Optimization)
        unique_risks = {}
        for r in risks:
            if r.document_id not in unique_risks or r.risk_score > unique_risks[r.document_id].risk_score:
                unique_risks[r.document_id] = r
        compressed_risks = list(unique_risks.values())

        unique_alerts = {}
        for a in alerts:
            if a.title not in unique_alerts:
                unique_alerts[a.title] = a
        compressed_alerts = list(unique_alerts.values())

        def doc_sort_key(d):
            sent = sentiment_map.get(d.id, 0.0)
            return (sent, d.published_at or d.collected_at)

        sorted_docs = sorted(documents, key=doc_sort_key)
        limited_docs = sorted_docs[:max_docs]

        # A3: Calculate Data Coverage
        data_coverage_data = self.calculate_data_coverage(
            db, client_id, entities, reputation, list(latest_execs.values()),
            list(latest_benchmarks.values()), compressed_risks, compressed_alerts, narratives, trends
        )

        # A4: Evaluate Context Quality
        context_quality = self.evaluate_context_quality(data_coverage_data["coverage_score"], limited_docs)

        # A9: Query previous reputation score (historical comparison)
        prev_reputation = db.query(ReputationScore).filter(
            ReputationScore.client_id == client_id,
            ReputationScore.created_at < start_naive
        ).order_by(ReputationScore.created_at.desc()).first()
        
        if not prev_reputation:
            prev_reputation = db.query(ReputationScore).filter(
                ReputationScore.client_id == client_id
            ).order_by(ReputationScore.created_at.desc()).offset(1).first()

        # 4. Serialize into Clean payload
        serialized_payload = {
            "client": serialize_client(client),
            "reputation": serialize_reputation(reputation),
            "entities": [serialize_entity(e) for e in entities],
            "executives": [serialize_executive_reputation(er) for er in latest_execs.values()],
            "benchmarks": [serialize_benchmark(bm, entity_names.get(bm.competitor_entity_id, "Unknown Competitor")) for bm in latest_benchmarks.values()],
            "risks": [serialize_risk_event(r) for r in compressed_risks[:max_risks]],
            "alerts": [serialize_alert(a) for a in compressed_alerts[:max_alerts]],
            "narratives": [serialize_narrative(n) for n in narratives[:max_narratives]],
            "trends": [serialize_trend_event(t) for t in trends[:10]],
            "documents": [serialize_document(d, sentiment_map.get(d.id), topic_map.get(d.id)) for d in limited_docs],
            "history": {
                "previous_reputation": serialize_reputation(prev_reputation) if prev_reputation else None
            },
            "metadata": {}  # Populated below
        }

        # A7: Token Budget Manager
        # Estimate size and compress if budget exceeded
        temp_json = json.dumps(serialized_payload, default=str)
        estimated_tokens = self.estimate_tokens(temp_json)
        actual_tokens = self.count_actual_tokens(temp_json)

        if actual_tokens > self.max_tokens:
            log.info("token_budget_exceeded_compressing", actual_tokens=actual_tokens, budget=self.max_tokens)
            # Compression Pass:
            serialized_payload["documents"] = serialized_payload["documents"][:3]
            serialized_payload["risks"] = serialized_payload["risks"][:3]
            serialized_payload["alerts"] = serialized_payload["alerts"][:3]
            serialized_payload["narratives"] = serialized_payload["narratives"][:2]
            
            # Recalculate size
            temp_json = json.dumps(serialized_payload, default=str)
            estimated_tokens = self.estimate_tokens(temp_json)
            actual_tokens = self.count_actual_tokens(temp_json)
            log.info("token_budget_compression_completed", new_actual_tokens=actual_tokens)

        # 5. Metadata, Stats, and Validation
        build_duration_ms = (time.perf_counter() - t0) * 1000
        payload_size_kb = round(len(temp_json) / 1024.0, 2)
        
        # Calculate compression ratio
        raw_total = raw_docs_count + raw_risks_count + raw_alerts_count + raw_narratives_count + raw_trends_count
        compressed_total = len(serialized_payload["documents"]) + len(serialized_payload["risks"]) + len(serialized_payload["alerts"]) + len(serialized_payload["narratives"]) + len(serialized_payload["trends"])
        compression_ratio = round(raw_total / max(1, compressed_total), 2)

        stats = {
            "documents_loaded": raw_docs_count,
            "risks_loaded": raw_risks_count,
            "alerts_loaded": raw_alerts_count,
            "narratives_loaded": raw_narratives_count,
            "trends_loaded": raw_trends_count,
            "executives_loaded": len(latest_execs),
            "benchmarks_loaded": len(latest_benchmarks),
            "payload_size_kb": payload_size_kb,
            "estimated_tokens": estimated_tokens,
            "actual_tokens": actual_tokens,
            "compression_ratio": compression_ratio,
            "context_build_latency": round(build_duration_ms, 2)
        }

        # Determine last refresh timestamp
        last_refresh = None
        if reputation:
            last_refresh = reputation.created_at

        serialized_payload["metadata"] = {
            "context_version": self.context_version,
            "pipeline_version": self.pipeline_version,
            "generated_at": now_utc.isoformat(),
            "aggregation_run_id": reputation.run_id if reputation else None,
            "build_duration_ms": round(build_duration_ms, 2),
            "context_uuid": str(uuid.uuid4()),
            "client_last_refresh": last_refresh.isoformat() if last_refresh else None,
            "stats": stats,
            "data_coverage": data_coverage_data,
            "context_quality": context_quality
        }

        # Validate Context Payload
        validated_payload = validate_context_payload(serialized_payload)
        final_json = validated_payload.model_dump()

        # Update Cache
        if self.use_cache:
            context_cache.set(client_id, final_json)

        log.info(
            "context_build_finished",
            latency_ms=round(build_duration_ms, 2),
            context_size_bytes=len(temp_json),
            token_estimate=estimated_tokens,
            actual_tokens=actual_tokens,
            coverage_score=data_coverage_data["coverage_score"],
            context_quality=context_quality
        )

        return final_json
