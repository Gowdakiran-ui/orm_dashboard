"""Dashboard aggregate response cache (API_FORENSICS.md Section 6).

The dashboard polls a fixed set of per-client GET endpoints every 45s
(useDashboardData.ts's poll()). Two of them -- reputation-summary and
telemetry -- run genuinely heavy aggregate queries on every single poll
(reputation-summary: 7 separate grouped/joined queries; telemetry: loads
every document for the client into Python, then does 9 more full-table
scans) even though nothing usually changed between two consecutive polls.
The other 6 poll endpoints (risks, active-alerts, narratives, documents,
trend-events, collection status) are each a single filtered SELECT --
cheap enough that adding caching there in this pass isn't worth the extra
surface area; this can be extended the same way later if needed.

TTL-only for both: DASHBOARD_CACHE_TTL_SECONDS (30s) is under the 45s poll
interval, so a cache hit is never staler than the data the next poll would
have shown anyway -- both endpoints are populated purely by async Celery
engines (nothing in a synchronous request path writes to them), so there's
no user action that a short TTL would make confusingly invisible.

The one exception is reputation-summary's `executive_alert` field, which
reads Alert.is_acknowledged -- a user acknowledging an alert (alerts.py)
expects it gone immediately, not up-to-30s later. That write path calls
invalidate_client_dashboard_cache() explicitly instead of waiting out the TTL.
"""
import functools
import inspect
import json

from app.utils.redis_client import redis_client

DASHBOARD_CACHE_TTL_SECONDS = 30


def _cache_key(prefix: str, client_id) -> str:
    return f"dashboard:{prefix}:{client_id}"


def cached_by_client(prefix: str, ttl: int = DASHBOARD_CACHE_TTL_SECONDS):
    """Read-through cache for a GET endpoint shaped like
    `def handler(client_id: UUID, ..., response: Response, db: Session = Depends(get_db))`.

    Keyed by client_id. Sets X-Cache: HIT/MISS on the response for
    verification if the endpoint declares a `response: Response` parameter.
    """
    def decorator(func):
        sig = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            client_id = bound.arguments.get("client_id")
            response = bound.arguments.get("response")
            key = _cache_key(prefix, client_id)

            try:
                raw = redis_client.get(key)
            except Exception:
                raw = None

            if raw is not None:
                try:
                    cached = json.loads(raw)
                except (TypeError, ValueError):
                    cached = None
                if cached is not None:
                    if response is not None:
                        response.headers["X-Cache"] = "HIT"
                    return cached

            result = func(*args, **kwargs)

            if response is not None:
                response.headers["X-Cache"] = "MISS"
            try:
                redis_client.set(key, json.dumps(result, default=str), ex=ttl)
            except Exception:
                pass  # caching is an optimization; never break the response over it

            return result
        return wrapper
    return decorator


def invalidate_client_dashboard_cache(prefix: str, client_id) -> None:
    """Explicit bust for write paths where the TTL alone would leave a
    user-triggered change invisible for up to DASHBOARD_CACHE_TTL_SECONDS.
    """
    try:
        redis_client.delete(_cache_key(prefix, client_id))
    except Exception:
        pass
