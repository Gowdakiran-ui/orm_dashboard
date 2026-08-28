"""NLP inference result cache (API_FORENSICS.md Section 6).

Keyed by a hash of the exact model input (+ model name, + candidate labels
for topic classification, since the result depends on all of it) -- not by
document/client, so identical text reprocessed anywhere (a retry, a
syndicated duplicate, re-running a batch) hits cache regardless of which
document or client it came from. No auth/identity data is or should ever be
part of this key (Section 3 constraint #4) -- model output for a given text
is the same fact regardless of who's asking.

TTL is 30 days: the model is versioned (model_name baked into the key), so
a redeployed/upgraded model naturally misses instead of serving a stale
result under a reused key. Within one model version, the same input text
always produces the same output -- there is no real-world event that should
invalidate a cached NLP result before the model itself changes, so this is
TTL-only (no explicit-invalidation path, unlike the dashboard cache). The
TTL exists purely to bound Redis memory growth, not correctness.
"""
import hashlib
import json

from app.utils.redis_client import redis_client

NLP_CACHE_TTL_SECONDS = 30 * 24 * 3600


def make_key(namespace: str, model_name: str, *parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return f"nlp:{namespace}:{model_name}:{h.hexdigest()}"


def get_cached(key: str):
    try:
        raw = redis_client.get(key)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def set_cached(key: str, value) -> None:
    try:
        redis_client.set(key, json.dumps(value), ex=NLP_CACHE_TTL_SECONDS)
    except Exception:
        pass  # caching is an optimization; never break inference over it
