import re
from typing import List
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.models.user import ROLE_CLIENT_USER, ROLE_SUPER_ADMIN

VALID_ROLES = {ROLE_SUPER_ADMIN, ROLE_CLIENT_USER}

# Plain regex, not pydantic's EmailStr -- that needs the extra
# email-validator dependency (same reasoning as LoginRequest in
# schemas/auth.py). Just enough to reject something like "example.gmail.com"
# (confirmed live -- got accepted as a real account before this) without
# pulling in RFC 5322 edge-case handling nobody here needs.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class CreateUserRequest(BaseModel):
    email: str
    role: str = ROLE_CLIENT_USER
    client_ids: List[UUID] = []

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        v = v.strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("email must be a valid address (e.g. name@example.com)")
        return v

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v


class UpdateUserClientsRequest(BaseModel):
    client_ids: List[UUID]


class AdminUserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    client_ids: List[str]


class CreateUserResponse(BaseModel):
    id: str
    email: str
    role: str
    password: str


class ResetPasswordResponse(BaseModel):
    id: str
    email: str
    password: str
