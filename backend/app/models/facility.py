"""Yard and StorageLocation models."""

from sqlalchemy import Column, String, Integer, Float, ForeignKey, Enum
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.models.base import Base, TimestampMixin


class YardStatusEnum(str, PyEnum):
    """Yard operational status."""
    ACTIVE = "Active"
    MAINTENANCE = "Maintenance"
    CLOSED = "Closed"


class StorageLocationStatusEnum(str, PyEnum):
    """Storage location availability status."""
    AVAILABLE = "Available"
    FULL = "Full"
    MAINTENANCE = "Maintenance"
    RESTRICTED = "Restricted"


class Yard(Base, TimestampMixin):
    """Shipyard facility."""
    __tablename__ = "yards"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    location = Column(String(200), nullable=False)
    capacity = Column(Float, nullable=False)  # Square meters or tonnage
    status = Column(Enum(YardStatusEnum), default=YardStatusEnum.ACTIVE, nullable=False)

    materials = relationship("Material", back_populates="yard")
    locations = relationship("StorageLocation", back_populates="yard")
    ships = relationship("Ship", back_populates="yard")

    def __repr__(self):
        return f"<Yard(id={self.id}, name={self.name})>"


class StorageLocation(Base, TimestampMixin):
    """Physical storage bin or zone."""
    __tablename__ = "storage_locations"

    id = Column(String(50), primary_key=True)
    yard_id = Column(String(50), ForeignKey("yards.id"), nullable=False)
    zone = Column(String(20), nullable=False)  # Zone identifier (A, B1, C2, etc.)
    aisle = Column(String(20), nullable=False)
    bin = Column(String(20))  # Optional: specific bin number
    capacity = Column(Integer, nullable=False)  # Max items or weight
    current_load = Column(Integer, default=0, nullable=False)
    status = Column(Enum(StorageLocationStatusEnum), default=StorageLocationStatusEnum.AVAILABLE, nullable=False)

    yard = relationship("Yard", back_populates="locations")
    materials = relationship("Material", back_populates="location")

    def __repr__(self):
        return f"<StorageLocation(id={self.id}, zone={self.zone}, aisle={self.aisle})>"
