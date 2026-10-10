"""Supplier model."""

from sqlalchemy import Column, String, Enum
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.models.base import Base, TimestampMixin


class SupplierStatusEnum(str, PyEnum):
    """Supplier approval and availability status."""
    APPROVED = "Approved"
    CONDITIONAL = "Conditional"
    PROBATION = "Probation"
    INACTIVE = "Inactive"
    BLOCKED = "Blocked"


class Supplier(Base, TimestampMixin):
    """Vendor and material supplier."""
    __tablename__ = "suppliers"

    id = Column(String(50), primary_key=True)
    name = Column(String(150), nullable=False, unique=True)
    contact_person = Column(String(100))
    contact_email = Column(String(100))
    contact_phone = Column(String(20))
    address = Column(String(300))
    country = Column(String(50))
    status = Column(Enum(SupplierStatusEnum), default=SupplierStatusEnum.APPROVED, nullable=False)
    notes = Column(String(500))

    def __repr__(self):
        return f"<Supplier(id={self.id}, name={self.name}, status={self.status})>"
