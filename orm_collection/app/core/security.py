"""Password hashing and Redis-backed session tokens (replaces the shared-
secret gate — see auth.py / TASK_AUTH.md, API_FORENSICS.md Section 1).

Sessions are opaque random tokens, not JWTs: the token itself carries no
information, it's just a lookup key into Redis (`session:<token>` -> JSON
payload with a TTL). Reuses the existing Redis instance (redis_client) rather
than adding a new session store, and -- unlike a stateless JWT -- logout can
actually revoke a session immediately by deleting its key.

Sessions are sliding-window, not a fixed expiry from login: both the Redis
TTL (get_session) and the browser cookie (set_session_cookie) are refreshed
to a fresh SESSION_TTL_SECONDS on every authenticated request (see
get_current_user in core/auth.py). A session only actually dies after
SESSION_TTL_SECONDS of genuine inactivity.
"""
import json
import secrets

import bcrypt
from fastapi import Response

from app.core.config import settings
from app.utils.redis_client import redis_client

SESSION_COOKIE_NAME = "orm_session"
SESSION_KEY_PREFIX = "session:"


def generate_password() -> str:
    """Cryptographically random password for admin-generated accounts
    (TASK_ONBOARDING.md -- replaces the invite/SMTP flow). 24 bytes of
    secrets.token_urlsafe entropy (~32 URL-safe chars) -- genuinely strong,
    not a weak/guessable scheme. Caller is responsible for returning this to
    the admin exactly once; nothing here logs or persists the plaintext.
    """
    return secrets.token_urlsafe(24)


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed/unrecognized hash -- never let this look like a match.
        return False


def create_session(user_id, email: str) -> str:
    """Create a new session, store it in Redis, return the opaque token."""
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": str(user_id), "email": email})
    redis_client.set(f"{SESSION_KEY_PREFIX}{token}", payload, ex=settings.SESSION_TTL_SECONDS)
    return token


def get_session(token: str) -> dict | None:
    """Look up a session and, if found, slide its Redis TTL forward by
    another SESSION_TTL_SECONDS -- so an actively-used session doesn't
    expire out from under the user mid-session (was previously a fixed TTL
    set once at create_session() and never renewed).
    """
    key = f"{SESSION_KEY_PREFIX}{token}"
    raw = redis_client.get(key)
    if not raw:
        return None
    try:
        session = json.loads(raw)
    except (TypeError, ValueError):
        return None
    try:
        redis_client.expire(key, settings.SESSION_TTL_SECONDS)
    except Exception:
        # Renewal is best-effort: a transient Redis error here shouldn't
        # invalidate an otherwise-valid session for *this* request. Worst
        # case the TTL isn't extended and the session expires on its
        # original schedule -- already logged by redis_client.expire().
        pass
    return session


def delete_session(token: str) -> None:
    redis_client.delete(f"{SESSION_KEY_PREFIX}{token}")


def set_session_cookie(response: Response, token: str) -> None:
    """Single source of truth for the session cookie's attributes -- used
    both at login (fresh session) and on every authenticated request (to
    slide the cookie's own expiry forward in lockstep with the Redis TTL
    renewal in get_session(); the cookie previously carried a fixed max_age
    from login and was never re-set, so it silently expired client-side on
    its own schedule even while the Redis session was still valid).
    """
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
        # Hardcoded for now -- should become a COOKIE_DOMAIN setting/env var
        # if another domain is ever added.
        domain=".theaicompany.co",
    )
