"""
Run Pipeline cost meter: what one pipeline run cost, per run and per client, in `pipeline_run_costs`
(database/migrations/0020_add_pipeline_run_costs.sql).

What is recorded, and how reliable each number is:
  * Apify (Reddit, Instagram): Reddit's actor reports its own `usageTotalUsd` (read from the finished run, exact). Instagram is called
    through the synchronous endpoint, which returns no usage, so it is ESTIMATED as results x $0.0027 (the documented per-result
    price, adapters/instagram.py) and flagged `apify_cost_estimated`.
  * LLM: calls and tokens come from `llm_call_log` for this client during the run's time window (any other LLM call for the same
    client in that window, for example the hourly risk job, is included); the dollar figure is ESTIMATED from the token counts at the
    public per-token price of the model each call type uses (LLM_PRICES). A call type with no listed price is counted but costs 0
    and is named in `llm_by_type[...]["price_known"] = false`.
  * Search calls: keyword searches the run made (search cursors touched during the run), by source.

Everything here is best-effort: it never raises into a pipeline stage, and it uses its own short database session so it can never
interact with a stage's transaction (same approach as utils/llm_call_logging.py). No score, risk or report reads it.
"""
import datetime
import uuid
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import func, text

logger = structlog.get_logger()

# Apify apify/instagram-scraper, PAY_PER_EVENT, free tier: $2.70 per 1000 results (adapters/instagram.py, confirmed 2026-09-12).
INSTAGRAM_USD_PER_RESULT = 0.0027

# Public OpenRouter prices, USD per million tokens (input, output), read from https://openrouter.ai/api/v1/models on 2026-11-09.
LLM_PRICES: Dict[str, Dict[str, Any]] = {
    "risk_role_classify": {"model": "deepseek/deepseek-v4-pro", "in": 0.95526, "out": 1.91052},
    "ai_summary_generate": {"model": "deepseek/deepseek-v4-pro", "in": 0.95526, "out": 1.91052},
    "risk_case_status": {"model": "anthropic/claude-haiku-4.5", "in": 1.0, "out": 5.0},
    "risk_penalty_parse": {"model": "anthropic/claude-haiku-4.5", "in": 1.0, "out": 5.0},
}


def llm_cost_usd(call_type: str, tokens_prompt: int, tokens_completion: int) -> Optional[float]:
    """Estimated dollars for these tokens, or None when the call type has no listed price."""
    p = LLM_PRICES.get(call_type)
    if not p:
        return None
    return ((tokens_prompt or 0) * p["in"] + (tokens_completion or 0) * p["out"]) / 1_000_000.0


def _uuid(value):
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _session(db):
    if db is not None:
        return db, False
    from app.core.db import SessionLocal
    return SessionLocal(), True


def _row(db, run_id: str, client_id):
    from app.models.pipeline_run_cost import PipelineRunCost
    row = db.query(PipelineRunCost).filter(PipelineRunCost.run_id == run_id).first()
    if row is None:
        row = PipelineRunCost(run_id=run_id, client_id=client_id, apify_calls=0, apify_cost_usd=0.0, apify_cost_estimated=False,
                              llm_calls=0, llm_tokens_prompt=0, llm_tokens_completion=0, llm_est_cost_usd=0.0, search_calls=0, finalized=False)
        db.add(row)
        db.flush()
    return row


def record_apify_usage(run_id: str, client_id, source_type: str, usd: Optional[float], estimated: bool, db=None) -> bool:
    """Add one Apify call to the run's row. `usd` None = the cost could not be read (counted, costs 0, flagged estimated).
    Best-effort: returns False instead of raising."""
    s, own = _session(db)
    try:
        row = _row(s, run_id, _uuid(client_id))
        unknown = usd is None
        amount = 0.0 if unknown else float(usd)
        est = bool(estimated or unknown)
        by = dict(row.apify_by_source or {})
        cur = dict(by.get(source_type) or {"calls": 0, "usd": 0.0, "estimated": False})
        cur.update(calls=cur["calls"] + 1, usd=round(cur["usd"] + amount, 6), estimated=bool(cur["estimated"] or est))
        by[source_type] = cur
        row.apify_by_source = by
        row.apify_calls = (row.apify_calls or 0) + 1
        row.apify_cost_usd = round((row.apify_cost_usd or 0.0) + amount, 6)
        row.apify_cost_estimated = bool(row.apify_cost_estimated or est)
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        s.commit()
        return True
    except Exception as exc:
        s.rollback()
        logger.warning("pipeline_cost_apify_record_failed", run_id=run_id, source=source_type, error=str(exc))
        return False
    finally:
        if own:
            s.close()


def record_social_search(run_id: str, client_id, source_type: str, adapter: Any, results_returned: int, db=None) -> bool:
    """Called by the collection stage after one Apify-backed search. Reddit's adapter exposes `last_usage_usd` (the actor's reported
    usage); Instagram has none, so its cost is estimated from the result count. Anything else is counted with an unknown cost."""
    usd = getattr(adapter, "last_usage_usd", None)
    estimated = False
    if usd is None and source_type == "instagram":
        usd, estimated = results_returned * INSTAGRAM_USD_PER_RESULT, True
    return record_apify_usage(run_id, client_id, source_type, usd, estimated, db=db)


def finalize_run_cost(run_id: str, client_id, db=None, now: Optional[datetime.datetime] = None) -> bool:
    """Fill in LLM and search figures at the end of a run and mark the row final. Best-effort."""
    from app.models.entity import Entity, EntityKeyword
    from app.models.pipeline_run import PipelineRun
    from app.models.search import SearchCursor

    s, own = _session(db)
    try:
        cid = _uuid(client_id)
        run = s.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
        started = run.started_at if run and run.started_at else None
        end = now or datetime.datetime.now(datetime.timezone.utc)
        row = _row(s, run_id, cid)
        llm_by: Dict[str, Any] = {}
        calls = tp = tc = 0
        total = 0.0
        if started is not None:
            for call_type, n, p, c, failed in s.execute(
                text("SELECT call_type, COUNT(*), COALESCE(SUM(tokens_prompt), 0), COALESCE(SUM(tokens_completion), 0), "
                     "SUM(CASE WHEN success THEN 0 ELSE 1 END) FROM llm_call_log "
                     "WHERE client_id = :cid AND created_at >= :a AND created_at <= :b GROUP BY call_type"),
                {"cid": str(cid), "a": started, "b": end},
            ).fetchall():
                cost = llm_cost_usd(call_type, int(p), int(c))
                llm_by[call_type] = {"calls": int(n), "failed": int(failed or 0), "tokens_prompt": int(p), "tokens_completion": int(c),
                                     "est_usd": round(cost, 6) if cost is not None else 0.0, "price_known": cost is not None,
                                     "model": (LLM_PRICES.get(call_type) or {}).get("model")}
                calls, tp, tc = calls + int(n), tp + int(p), tc + int(c)
                total += cost or 0.0
        search_by: Dict[str, int] = {}
        if started is not None:
            for source, n in s.query(SearchCursor.source_type, func.count(SearchCursor.id)).join(
                    EntityKeyword, EntityKeyword.id == SearchCursor.keyword_id).join(Entity, Entity.id == EntityKeyword.entity_id).filter(
                    Entity.client_id == cid, SearchCursor.last_searched_at >= started, SearchCursor.last_searched_at <= end
            ).group_by(SearchCursor.source_type).all():
                search_by[source] = int(n)
        row.llm_calls, row.llm_tokens_prompt, row.llm_tokens_completion = calls, tp, tc
        row.llm_est_cost_usd, row.llm_by_type = round(total, 6), llm_by
        row.search_calls, row.search_by_source = sum(search_by.values()), search_by
        row.finalized = True
        row.updated_at = datetime.datetime.now(datetime.timezone.utc)
        s.commit()
        return True
    except Exception as exc:
        s.rollback()
        logger.warning("pipeline_cost_finalize_failed", run_id=run_id, error=str(exc))
        return False
    finally:
        if own:
            s.close()


def last_run_cost(db, client_id) -> Optional[Dict[str, Any]]:
    """The client's most recent recorded run with its pipeline status, for the super-admin diagnostics panel."""
    from app.models.pipeline_run import PipelineRun
    from app.models.pipeline_run_cost import PipelineRunCost

    row = db.query(PipelineRunCost).filter(PipelineRunCost.client_id == _uuid(client_id)).order_by(
        PipelineRunCost.created_at.desc(), PipelineRunCost.updated_at.desc()).first()
    if row is None:
        return None
    run = db.query(PipelineRun).filter(PipelineRun.run_id == row.run_id).first()
    iso = lambda d: d.isoformat() if d else None
    return {
        "run_id": row.run_id, "finalized": bool(row.finalized),
        "run": None if run is None else {"status": run.status, "stage": run.stage, "started_at": iso(run.started_at),
                                         "finished_at": iso(run.finished_at), "duration_s": getattr(run, "duration_s", None)},
        "apify": {"calls": row.apify_calls, "cost_usd": row.apify_cost_usd, "estimated": bool(row.apify_cost_estimated), "by_source": row.apify_by_source or {}},
        "llm": {"calls": row.llm_calls, "tokens_prompt": row.llm_tokens_prompt, "tokens_completion": row.llm_tokens_completion,
                "est_cost_usd": row.llm_est_cost_usd, "by_type": row.llm_by_type or {}},
        "search": {"calls": row.search_calls, "by_source": row.search_by_source or {}},
        "total_usd": round((row.apify_cost_usd or 0.0) + (row.llm_est_cost_usd or 0.0), 6),
    }
