import time
import uuid
import os
import structlog
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

# Services
from app.services.ai.context_builder import ContextBuilder
from app.services.ai.prompt_builder import PromptBuilder
from app.services.ai.advisor.advisor_service import AdvisorService
from app.services.ai.crisis_planner.crisis_cache import crisis_cache
from app.services.ai.crisis_planner.crisis_validation import validate_crisis_response
from app.services.ai.crisis_planner.crisis_exceptions import CrisisPlannerException

logger = structlog.get_logger()

class CrisisPlanner:
    def __init__(
        self,
        use_cache: bool = True,
        model: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        from app.core.config import settings
        from app.services.ai.advisor.llm_providers import GroqProvider
        self.use_cache = use_cache
        self.context_builder = ContextBuilder(use_cache=use_cache)
        self.prompt_builder = PromptBuilder()
        
        provider = GroqProvider(
            api_key=api_key or os.environ.get("groq1") or os.environ.get("GROQ_API_KEY") or os.environ.get("groq"),
            model=model or settings.AI_MODEL,
            timeout=settings.AI_TIMEOUT_SECONDS,
            max_retries=settings.AI_MAX_RETRIES
        )
        self.advisor_service = AdvisorService(provider=provider)

    def generate_crisis_plan(
        self,
        db: Session,
        client_id: str,
        mode: str = "standard",
        temperature: float = 0.0,
        run_id: Optional[str] = None,
        batch_id: Optional[str] = None
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
            temperature=temperature,
            model=self.advisor_service.model,
            task="generate_crisis_plan"
        )
        log.info("crisis_planner_started")

        # 1. Check Cache
        if self.use_cache:
            cached_res = crisis_cache.get(client_id, mode, temperature)
            if cached_res:
                log.info("crisis_planner_cache_hit", latency_ms=round((time.perf_counter() - t0)*1000, 2))
                return cached_res

        try:
            # 2. Build Context
            t_ctx = time.perf_counter()
            if mode == "compact":
                context = self.context_builder.build_compact(db, client_id, run_id=rid, batch_id=bid)
            elif mode == "full":
                context = self.context_builder.build_full(db, client_id, run_id=rid, batch_id=bid)
            else:
                context = self.context_builder.build_standard(db, client_id, run_id=rid, batch_id=bid)
            
            ctx_lat = (time.perf_counter() - t_ctx) * 1000
            log.info("context_loaded", context_latency_ms=round(ctx_lat, 2))

            # Extract context metadata
            ctx_meta = context.get("metadata", {})
            coverage_score = ctx_meta.get("data_coverage", {}).get("coverage_score", 0.0)
            context_quality = ctx_meta.get("context_quality", "UNKNOWN")
            estimated_tokens = ctx_meta.get("stats", {}).get("estimated_tokens", 0)
            actual_tokens = ctx_meta.get("stats", {}).get("actual_tokens", 0)

            # 3. Generate Prompt Object
            t_prompt = time.perf_counter()
            prompt_obj = self.prompt_builder.build_prompt(context, "Crisis Planner", run_id=rid, batch_id=bid)
            prompt_lat = (time.perf_counter() - t_prompt) * 1000
            log.info("prompt_generated", prompt_latency_ms=round(prompt_lat, 2))

            # 4. Call Groq
            t_groq = time.perf_counter()
            groq_raw = self.advisor_service.call_groq(
                system_prompt=prompt_obj["system_prompt"],
                user_prompt=prompt_obj["user_prompt"],
                temperature=temperature,
                run_id=rid
            )
            groq_lat = (time.perf_counter() - t_groq) * 1000
            log.info("groq_request_finished", groq_latency_ms=round(groq_lat, 2))

            # 5. Validate Output
            validated = validate_crisis_response(groq_raw, context)
            final_response = validated.model_dump()

            # Add execution metadata
            req_id = str(uuid.uuid4())
            total_latency_ms = (time.perf_counter() - t0) * 1000
            
            final_response["metadata"] = {
                "run_id": rid,
                "batch_id": bid,
                "request_id": req_id,
                "client_id": client_id,
                "context_version": self.context_builder.context_version,
                "prompt_version": self.prompt_builder.prompt_version,
                "provider": "groq",
                "model": self.advisor_service.model,
                "temperature": temperature,
                "total_latency_ms": round(total_latency_ms, 2),
                "context_latency_ms": round(ctx_lat, 2),
                "prompt_latency_ms": round(prompt_lat, 2),
                "groq_latency_ms": round(groq_lat, 2),
                "context_quality": context_quality,
                "coverage_score": coverage_score,
                "estimated_tokens": estimated_tokens,
                "actual_tokens": actual_tokens,
                "cache_hit": False
            }

            # 6. Cache Response
            if self.use_cache:
                crisis_cache.set(client_id, mode, temperature, final_response)

            log.info(
                "crisis_planner_completed",
                request_id=req_id,
                total_latency_ms=round(total_latency_ms, 2),
                estimated_tokens=estimated_tokens,
                actual_tokens=actual_tokens,
                coverage=coverage_score,
                context_quality=context_quality
            )
            return final_response

        except Exception as e:
            log.error("crisis_planner_failed", error=str(e))
            
            # Construct safe fallback response
            fallback_response = {
                "executive_summary": "Insufficient evidence.",
                "current_assessment": f"An error occurred during crisis plan generation: {str(e)[:100]}",
                "severity": "LOW",
                "key_drivers": [],
                "business_impact": "Insufficient evidence.",
                "immediate_actions_24h": [],
                "short_term_actions_72h": [],
                "medium_term_actions_7d": [],
                "executive_communication": "Insufficient evidence.",
                "public_communication_strategy": "Insufficient evidence.",
                "stakeholder_actions": [],
                "monitoring_priorities": [],
                "success_metrics": [],
                "confidence": 0.0,
                "coverage": 0.0,
                "citations": {
                    "document_ids": [],
                    "narrative_ids": [],
                    "risk_ids": [],
                    "alert_ids": [],
                    "trend_ids": []
                },
                "metadata": {
                    "error": str(e)[:200],
                    "run_id": rid,
                    "batch_id": bid,
                    "worker_id": wid,
                    "total_latency_ms": round((time.perf_counter() - t0) * 1000, 2)
                }
            }
            return fallback_response

    def invalidate_cache(self, client_id: str):
        """Invalidates both context cache and crisis cache for a client."""
        self.context_builder.context_cache.invalidate(client_id)
        crisis_cache.invalidate(client_id)
