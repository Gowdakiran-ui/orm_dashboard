"""Redis-backed rate limiting (API_FORENSICS.md Section 2).

Still IP-only, not per-user, even after TASK_AUTH.md added real per-user
sessions (see auth.py) — switching the key_func to key off the
authenticated user is a deliberate follow-up (noted in TASK_AUTH.md), not
done in that pass, to keep that change scoped to auth alone.

GLOBAL_RATE_LIMIT is the default applied to every route; STRICT_RATE_LIMIT
is applied on top of routes that trigger NLP processing or a full pipeline
run, since those are what can actually overwhelm the single NLP worker.
Tune both here in one place.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

GLOBAL_RATE_LIMIT = "100/minute"
STRICT_RATE_LIMIT = "5/minute"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    default_limits=[GLOBAL_RATE_LIMIT],
    headers_enabled=True,  # needed for slowapi to set Retry-After on 429s
)
