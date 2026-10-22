"""User accounts, roles and sign-in sessions.

Passwords are stored only as scrypt hashes. A session is identified by a random token that the client
sends as a bearer token; only its SHA-256 digest is stored, so a database leak does not expose live tokens.
"""

from enum import Enum as PyEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, true
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class UserRole(str, PyEnum):
    ADMIN = "Admin"
    STOREKEEPER = "Storekeeper"
    PROCUREMENT = "Procurement"
    INSPECTOR = "Inspector"
    VIEWER = "Viewer"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True, index=True)  # stored lower-case
    display_name = Column(String(100), nullable=False)
    email = Column(String(200))
    role = Column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    password_hash = Column(String(300), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    last_login_at = Column(DateTime)

    sessions = relationship("UserSession", back_populates="user")


class UserSession(Base):
    __tablename__ = "user_sessions"

    token_hash = Column(String(64), primary_key=True)  # SHA-256 hex of the bearer token
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)

    user = relationship("User", back_populates="sessions")
