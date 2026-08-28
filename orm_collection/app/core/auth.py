from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import SESSION_COOKIE_NAME, get_session
from app.models.user import ROLE_SUPER_ADMIN, User, UserClientAccess


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    """Real per-user auth (replaces the platform-wide shared-secret gate --
    API_FORENSICS.md Section 1). Reads the httpOnly session cookie, looks it
    up in Redis, and loads the corresponding user.
    """
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = get_session(session_token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")

    user = db.query(User).filter(User.id == session["user_id"], User.is_active == True).first()  # noqa: E712
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def user_has_client_access(db: Session, user_id, client_id) -> bool:
    return (
        db.query(UserClientAccess)
        .filter(UserClientAccess.user_id == user_id, UserClientAccess.client_id == client_id)
        .first()
        is not None
    )


def require_client_access(
    client_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UUID:
    """Per-request tenant authorization dependency.

    `client_id` is resolved by FastAPI from whatever the calling route
    already exposes it as (path param or query param) -- attach this as an
    extra dependency to any route/router that takes a client_id and it's
    verified for free. For a client_id that only exists in a request BODY
    (not path/query), use user_has_client_access() directly instead, since
    FastAPI dependencies can't read the body of a sibling parameter.

    A super_admin bypasses the user_client_access check entirely (TASK_ROLES.md
    -- "sees every client" is the whole point of the role).
    """
    if current_user.role == ROLE_SUPER_ADMIN:
        return client_id
    if not user_has_client_access(db, current_user.id, client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this client")
    return client_id


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Gate for user-management endpoints (TASK_ROLES.md) -- mirrors
    require_client_access's style. No client_user, regardless of which
    client(s) they're granted, may reach an endpoint behind this.
    """
    if current_user.role != ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return current_user
