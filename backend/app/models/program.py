"""Ship and ShipSeries models."""

from sqlalchemy import Column, String, Integer, Float, ForeignKey, Date, Enum
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.models.base import Base, TimestampMixin


class ShipBuildStatusEnum(str, PyEnum):
    """Ship build program status."""
    PLANNING = "Planning"
    FABRICATION = "Fabrication"
    ASSEMBLY = "Assembly"
    OUTFITTING = "Outfitting"
    SYSTEMS_INTEGRATION = "Systems integration"
    TESTING = "Testing"
    LAUNCH_READY = "Launch ready"
    LAUNCHED = "Launched"
    COMMISSIONED = "Commissioned"


class ShipSeries(Base, TimestampMixin):
    """Ship design series or program line."""
    __tablename__ = "ship_series"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(500))
    design_spec = Column(String(200))  # e.g., "Bulk carrier", "Tanker", "Container ship"

    ships = relationship("Ship", back_populates="series")

    def __repr__(self):
        return f"<ShipSeries(id={self.id}, name={self.name})>"


class Ship(Base, TimestampMixin):
    """Individual vessel under construction."""
    __tablename__ = "ships"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    series_id = Column(String(50), ForeignKey("ship_series.id"), nullable=False)
    yard_id = Column(String(50), ForeignKey("yards.id"), nullable=False)
    build_status = Column(Enum(ShipBuildStatusEnum), default=ShipBuildStatusEnum.PLANNING, nullable=False)
    build_progress = Column(Integer, default=0, nullable=False)  # Percentage 0-100
    allocated_value = Column(Float, nullable=False)  # USD or local currency
    material_line_count = Column(Integer, default=0, nullable=False)
    scheduled_launch = Column(Date)
    scheduled_commissioning = Column(Date)

    series = relationship("ShipSeries", back_populates="ships")
    yard = relationship("Yard", back_populates="ships")
    materials = relationship("Material", back_populates="ship")

    def __repr__(self):
        return f"<Ship(id={self.id}, name={self.name}, progress={self.build_progress}%)>"
