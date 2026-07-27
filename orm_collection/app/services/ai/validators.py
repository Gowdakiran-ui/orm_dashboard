import structlog
import uuid
import datetime
from typing import Any, Dict, Optional
from app.services.ai.schemas import AIContextPayload, ClientContext, ContextMetadata, ContextStats, DataCoverage

logger = structlog.get_logger()

def validate_context_payload(payload_dict: Dict[str, Any]) -> AIContextPayload:
    """
    Validates a serialized context dictionary against the Pydantic AIContextPayload schema.
    If the client is missing, we raise a ValueError since it's the core of the context.
    If other components are missing, we log a warning and return graceful defaults.
    """
    # Verify client is present
    if "client" not in payload_dict or not payload_dict["client"]:
        raise ValueError("Cannot validate context payload: client information is missing.")

    # Generate dummy metadata if missing
    if "metadata" not in payload_dict or not payload_dict["metadata"]:
        dummy_stats = ContextStats(
            documents_loaded=0,
            risks_loaded=0,
            alerts_loaded=0,
            narratives_loaded=0,
            trends_loaded=0,
            executives_loaded=0,
            benchmarks_loaded=0,
            payload_size_kb=0.0,
            estimated_tokens=0,
            compression_ratio=1.0,
            context_build_latency=0.0
        )
        dummy_coverage = DataCoverage(
            coverage_score=0.0,
            coverage_reason="Dummy metadata",
            missing_sources=["all"],
            enabled_sources=[]
        )
        payload_dict["metadata"] = {
            "context_version": "1.0.0",
            "pipeline_version": "1.0.0",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "aggregation_run_id": None,
            "build_duration_ms": 0.0,
            "context_uuid": str(uuid.uuid4()),
            "client_last_refresh": None,
            "stats": dummy_stats.model_dump(),
            "data_coverage": dummy_coverage.model_dump(),
            "context_quality": "LOW"
        }

    # Apply graceful defaults for other missing keys
    graceful_payload = {
        "client": payload_dict["client"],
        "reputation": payload_dict.get("reputation"),
        "entities": payload_dict.get("entities") or [],
        "executives": payload_dict.get("executives") or [],
        "benchmarks": payload_dict.get("benchmarks") or [],
        "risks": payload_dict.get("risks") or [],
        "alerts": payload_dict.get("alerts") or [],
        "narratives": payload_dict.get("narratives") or [],
        "trends": payload_dict.get("trends") or [],
        "documents": payload_dict.get("documents") or [],
        "history": payload_dict.get("history"),
        "metadata": payload_dict["metadata"]
    }

    # Verify and log warnings for missing critical components
    client_id = graceful_payload["client"].get("id")
    if not graceful_payload["reputation"]:
        logger.warning("validation_warning_missing_reputation", client_id=client_id)
    if not graceful_payload["executives"]:
        logger.warning("validation_warning_missing_executives", client_id=client_id)
    if not graceful_payload["benchmarks"]:
        logger.warning("validation_warning_missing_benchmarks", client_id=client_id)
    if not graceful_payload["risks"]:
        logger.warning("validation_warning_missing_risks", client_id=client_id)
    if not graceful_payload["narratives"]:
        logger.warning("validation_warning_missing_narratives", client_id=client_id)

    try:
        return AIContextPayload(**graceful_payload)
    except Exception as e:
        logger.error("validation_schema_parsing_failed_falling_back", error=str(e))
        # Fallback to a minimal valid payload if validation fails due to some type mismatch
        fallback_client = ClientContext(**graceful_payload["client"])
        fallback_meta = ContextMetadata(**graceful_payload["metadata"])
        return AIContextPayload(client=fallback_client, metadata=fallback_meta)
