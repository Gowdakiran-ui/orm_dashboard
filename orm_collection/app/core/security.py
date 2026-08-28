"""Password hashing and Redis-backed session tokens (replaces the shared-
secret gate — see auth.py / TASK_AUTH.md, API_FORENSICS.md Section 1).

Sessions are opaque random tokens, not JWTs: the token itself carries no
information, it's just a lookup key into Redis (`session:<token>` -> JSON
payload with a TTL). Reuses the existing Redis instance (redis_client) rather
than adding a new session store, and -- unlike a stateless JWT -- logout can
actually revoke a session immediately by deleting its key.
"""
import json
import secrets

import bcrypt

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
    raw = redis_client.get(f"{SESSION_KEY_PREFIX}{token}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def delete_session(token: str) -> None:
    redis_client.delete(f"{SESSION_KEY_PREFIX}{token}")
