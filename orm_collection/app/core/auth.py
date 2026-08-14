import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(_api_key_header)) -> None:
    """Shared-secret gate applied to every router except /health.

    Not a per-user/role auth system — answers only "is this caller allowed
    to use the API at all" (API_FORENSICS.md Section 2 / TASK.md Phase 1).
    """
    if not settings.API_SHARED_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_SHARED_SECRET is not configured on the server",
        )
    if not api_key or not secrets.compare_digest(api_key, settings.API_SHARED_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
