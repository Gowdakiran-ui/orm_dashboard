import uuid
from sqlalchemy import CheckConstraint, Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.db import Base

ROLE_SUPER_ADMIN = "super_admin"
ROLE_CLIENT_USER = "client_user"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    # NOT NULL again (TASK_ONBOARDING.md -- replaces the invite/SMTP flow):
    # a super_admin generates the password server-side and the account is
    # active from the moment it's created, so there's no pending/inactive
    # window where a user could exist without one.
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    role = Column(String(20), nullable=False, default=ROLE_CLIENT_USER, server_default=ROLE_CLIENT_USER)

    client_access = relationship("UserClientAccess", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(f"role IN ('{ROLE_SUPER_ADMIN}', '{ROLE_CLIENT_USER}')", name="ck_users_role"),
    )


class UserClientAccess(Base):
    """Tenant-authorization mapping: which client_id(s) a user may access.

    No implicit access -- a user with zero rows here can see zero clients
    (API_FORENSICS.md Section 1 / TASK_AUTH.md fix #1).
    """
    __tablename__ = "user_client_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="client_access")

    __table_args__ = (
        UniqueConstraint("user_id", "client_id", name="uq_user_client_access"),
    )
