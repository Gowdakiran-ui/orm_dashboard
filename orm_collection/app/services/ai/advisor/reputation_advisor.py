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
from app.services.ai.advisor.advisor_cache import advisor_cache
from app.services.ai.advisor.advisor_validation import validate_advisor_response
from app.services.ai.advisor.advisor_exceptions import AdvisorException

logger = structlog.get_logger()

class ReputationAdvisor:
    def __init__(
        self,
        use_cache: bool = True,
        model: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.use_cache = use_cache
        self.context_builder = ContextBuilder(use_cache=use_cache)
        self.prompt_builder = PromptBuilder()
        self.advisor_service = AdvisorService(model=model, api_key=api_key)

    def generate_reputation_advice(
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
            task="generate_reputation_advice"
        )
        log.info("advisor_started")

        # 1. Check Cache
        if self.use_cache:
            cached_res = advisor_cache.get(client_id, mode, temperature)
            if cached_res:
                log.info("advisor_cache_hit", latency_ms=round((time.perf_counter() - t0)*1000, 2))
                return cached_res

        try:
            # 2. Build Context based on mode
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
            prompt_obj = self.prompt_builder.build_prompt(context, "AI Reputation Advisor", run_id=rid, batch_id=bid)
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
            validated = validate_advisor_response(groq_raw, context)
            final_response = validated.model_dump()

            # A7: Request Traceability
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
                advisor_cache.set(client_id, mode, temperature, final_response)

            log.info(
                "advisor_completed",
                request_id=req_id,
                total_latency_ms=round(total_latency_ms, 2),
                estimated_tokens=estimated_tokens,
                actual_tokens=actual_tokens,
                coverage=coverage_score,
                context_quality=context_quality
            )
            return final_response

        except Exception as e:
            # Handle error gracefully without exposing sensitive information or stack traces
            log.error("advisor_failed", error=str(e))
            
            # Construct a safe fallback response
            fallback_response = {
                "overall_assessment": "Insufficient evidence.",
                "executive_summary": f"An error occurred during advisor generation: {str(e)[:100]}",
                "current_reputation": "Insufficient evidence.",
                "strengths": [],
                "weaknesses": [],
                "major_risks": [],
                "positive_signals": [],
                "negative_signals": [],
                "executive_analysis": [],
                "competitor_position": [],
                "trend_analysis": "Insufficient evidence.",
                "priority_actions_24h": [],
                "priority_actions_7d": [],
                "priority_actions_30d": [],
                "opportunities": [],
                "predicted_business_impact": "Insufficient evidence.",
                "confidence": 0.0,
                "coverage": 0.0,
                "limitations": ["Advisor processing failed."],
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
        """Invalidates both context cache and advisor cache for a client."""
        context_cache.invalidate(client_id)
        advisor_cache.invalidate(client_id)
