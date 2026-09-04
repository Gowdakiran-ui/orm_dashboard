import uuid
import structlog

logger = structlog.get_logger()


def log_llm_call(call_type: str, client_id, run_id: str = None,
                  tokens_prompt: int = None, tokens_completion: int = None,
                  latency_ms: float = None, success: bool = True):
    """
    Best-effort persisted record of one OpenRouter call, for cost/volume
    observability (there was previously no DB record of LLM call counts
    or token usage anywhere -- only ephemeral stdout logs, which are lost
    on every container recreate).

    Opens its own short-lived session rather than reuse the caller's --
    _llm_classify_role and _attempt_split_call run inside a savepoint-
    nested batch transaction (risk_engine.process_client) or a per-topic
    loop (narrative_engine.calculate_narratives), and this insert must
    never interact with that transaction's state or its rollback/commit
    timing. Any failure here (DB unreachable, connection ceiling, etc.)
    is caught and logged, never raised -- this must never block or fail
    the actual LLM call it's recording.
    """
    try:
        from app.core.db import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            db.execute(
                text("""
                    INSERT INTO llm_call_log (
                        id, call_type, client_id, run_id, tokens_prompt,
                        tokens_completion, latency_ms, success
                    ) VALUES (
                        :id, :call_type, :client_id, :run_id, :tokens_prompt,
                        :tokens_completion, :latency_ms, :success
                    )
                """),
                {
                    "id": uuid.uuid4(),
                    "call_type": call_type,
                    "client_id": client_id,
                    "run_id": run_id,
                    "tokens_prompt": tokens_prompt,
                    "tokens_completion": tokens_completion,
                    "latency_ms": latency_ms,
                    "success": success,
                }
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("llm_call_log_insert_failed", call_type=call_type, error=str(exc))
