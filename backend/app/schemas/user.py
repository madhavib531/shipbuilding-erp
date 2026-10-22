"""Schemas for sign-in and user administration."""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.user import UserRole

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class LoginRequest(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    password: Password


class PasswordChange(BaseModel):
    current_password: Password
    new_password: Password


class PasswordReset(BaseModel):
    new_password: Password


class UserCreate(BaseModel):
    username: Username
    display_name: DisplayName
    role: UserRole
    password: Password
    email: Optional[Email] = None


class UserUpdate(BaseModel):
    display_name: Optional[DisplayName] = None
    email: Optional[Email] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    email: Optional[str]
    role: UserRole
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime


class Me(UserRead):
    permissions: list[str] = Field(default_factory=list)
