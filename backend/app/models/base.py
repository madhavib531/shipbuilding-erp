"""Base model with common attributes."""

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, DateTime, func
from datetime import datetime


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class TimestampMixin:
    """Mixin providing created_at and updated_at timestamps."""
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
