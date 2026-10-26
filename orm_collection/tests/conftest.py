"""Refuse to run the test suite against a non-local database.

The local .env points DATABASE_URL at the production managed Postgres, and some engines open their own
SessionLocal (bypassing the tests' SQLite fixtures), so a plain `pytest` could read/write prod and call a
paid LLM. Local hosts and the compose service names are allowed; set ALLOW_REMOTE_DB_TESTS=1 to override.
"""
import os
import sys
from urllib.parse import urlparse

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}


def pytest_sessionstart(session):
    if os.environ.get("ALLOW_REMOTE_DB_TESTS") == "1":
        return
    from app.core.config import settings
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        return
    host = (urlparse(url).hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        pytest.exit(
            f"Refusing to run tests: DATABASE_URL points at remote host '{host}'. Point DATABASE_URL at a "
            "local/throwaway DB (e.g. DATABASE_URL=postgresql://x:x@127.0.0.1:1/none) or set ALLOW_REMOTE_DB_TESTS=1.",
            returncode=3,
        )
