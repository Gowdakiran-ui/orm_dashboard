from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_super_admin
from app.core.db import get_db
from app.core.security import generate_password, hash_password
from app.models.user import ROLE_SUPER_ADMIN, User, UserClientAccess
from app.schemas.admin_users import (
    AdminUserResponse,
    CreateUserRequest,
    CreateUserResponse,
    ResetPasswordResponse,
    UpdateUserClientsRequest,
)

router = APIRouter()


def _to_admin_response(db: Session, user: User) -> AdminUserResponse:
    client_ids = [
        str(row.client_id)
        for row in db.query(UserClientAccess.client_id).filter(UserClientAccess.user_id == user.id).all()
    ]
    return AdminUserResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        client_ids=client_ids,
    )


@router.post("", response_model=CreateUserResponse)
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    """Replaces the old invite/SMTP flow (TASK_ONBOARDING.md) -- no email
    involved anywhere. Generates a strong password server-side, hashes it,
    and creates the account active immediately; the plaintext password is
    returned in THIS response only -- never stored, never logged (the
    structlog request-logging middleware in main.py logs only path/method/
    status/latency, never the body, so nothing else in this codebase can
    leak it either).
    """
    email = body.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="A user with this email already exists")

    plaintext_password = generate_password()
    user = User(
        email=email,
        password_hash=hash_password(plaintext_password),
        is_active=True,
        role=body.role,
    )
    db.add(user)
    db.flush()  # assigns user.id before creating the UserClientAccess rows below

    # super_admin sees every client by design (require_client_access's
    # bypass) -- explicit grants are meaningless for that role, so any
    # client_ids passed alongside role=super_admin are ignored rather than
    # silently accepted as a no-op that looks like it did something.
    if body.role != ROLE_SUPER_ADMIN:
        for client_id in body.client_ids:
            db.add(UserClientAccess(user_id=user.id, client_id=client_id))

    db.commit()
    db.refresh(user)

    return CreateUserResponse(id=str(user.id), email=user.email, role=user.role, password=plaintext_password)


@router.get("/", response_model=list[AdminUserResponse])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_super_admin)):
    # A super_admin sees every client_user plus their own row -- but not
    # other super_admins (there are only ever a handful, and they shouldn't
    # be visible to/manageable by each other through this list).
    users = db.query(User).filter(
        (User.role != ROLE_SUPER_ADMIN) | (User.id == current_user.id)
    ).order_by(User.email).all()
    return [_to_admin_response(db, u) for u in users]


@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    user_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    """Generates a new password and returns it once (same one-time-only
    contract as create_user above); doesn't otherwise touch role or client
    access.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    plaintext_password = generate_password()
    target.password_hash = hash_password(plaintext_password)
    db.commit()

    return ResetPasswordResponse(id=str(target.id), email=target.email, password=plaintext_password)


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _admin: User = Depends(require_super_admin),
):
    """Hard delete -- matches the existing convention in this codebase
    (clients.py's DELETE /{client_id} is also a real, irreversible delete,
    not a soft one). user_client_access rows cascade away with it
    (ondelete=CASCADE), and nothing else references users.id, so a hard
    delete also frees the email up immediately for a fresh re-creation --
    a soft delete would leave the row blocking that.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if str(target.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    if target.role == ROLE_SUPER_ADMIN:
        active_super_admins = db.query(User).filter(
            User.role == ROLE_SUPER_ADMIN,
            User.is_active == True,  # noqa: E712
        ).count()
        if active_super_admins <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last remaining super_admin")

    db.delete(target)
    db.commit()
    return {"status": "deleted", "id": str(user_id)}


@router.patch("/{user_id}/clients", response_model=AdminUserResponse)
def update_user_clients(
    user_id: str,
    body: UpdateUserClientsRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_super_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.role == ROLE_SUPER_ADMIN:
        raise HTTPException(status_code=400, detail="Client scoping does not apply to super_admin users")

    db.query(UserClientAccess).filter(UserClientAccess.user_id == target.id).delete(synchronize_session=False)
    for client_id in body.client_ids:
        db.add(UserClientAccess(user_id=target.id, client_id=client_id))
    db.commit()

    return _to_admin_response(db, target)
