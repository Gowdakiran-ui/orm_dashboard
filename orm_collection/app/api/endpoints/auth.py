from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.rate_limit import limiter, STRICT_RATE_LIMIT
from app.core.security import SESSION_COOKIE_NAME, create_session, delete_session, verify_password
from app.models.user import User, UserClientAccess
from app.schemas.auth import LoginRequest, MeResponse, UserResponse

router = APIRouter()


def _set_session_cookie(response: Response, token: str) -> None:
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


@router.post("/login", response_model=UserResponse)
@limiter.limit(STRICT_RATE_LIMIT)
def login(request: Request, body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Strict-rate-limited (credential-stuffing) — mirrors the tier already
    applied to other expensive/abusable routes (rate_limit.py).
    """
    user = db.query(User).filter(User.email == body.email.strip().lower(), User.is_active == True).first()  # noqa: E712
    if not user or not verify_password(body.password, user.password_hash):
        # Same 401 for "no such user" and "wrong password" -- doesn't leak
        # which one it was.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_session(user.id, user.email)
    _set_session_cookie(response, token)

    return {"id": str(user.id), "email": user.email}


@router.post("/logout")
def logout(response: Response, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME)):
    if session_token:
        delete_session(session_token)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Used by the frontend both to check auth state and to populate the
    tenant dropdown with only the clients this user is actually granted
    (never a hardcoded/full list — API_FORENSICS.md Section 1).
    """
    client_ids = [
        str(row.client_id)
        for row in db.query(UserClientAccess).filter(UserClientAccess.user_id == current_user.id).all()
    ]
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role,
        "client_ids": client_ids,
    }
