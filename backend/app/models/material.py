"""Material and MaterialCategory models."""

from sqlalchemy import Column, String, Integer, Float, ForeignKey, Enum
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.models.base import Base, TimestampMixin


class MaterialStatusEnum(str, PyEnum):
    """Material status enumeration."""
    HEALTHY = "Healthy"
    LOW_STOCK = "Low stock"
    INSPECTION = "Inspection"
    RESERVED = "Reserved"


class MaterialCategory(Base, TimestampMixin):
    """Material classification."""
    __tablename__ = "material_categories"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(500))

    materials = relationship("Material", back_populates="category")

    def __repr__(self):
        return f"<MaterialCategory(id={self.id}, name={self.name})>"


class Material(Base, TimestampMixin):
    """Inventory material item."""
    __tablename__ = "materials"

    id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    category_id = Column(String(50), ForeignKey("material_categories.id"), nullable=False)
    batch = Column(String(50), nullable=False)
    quantity = Column(Integer, default=0, nullable=False)
    available = Column(Integer, default=0, nullable=False)
    reserved = Column(Integer, default=0, nullable=False)
    unit = Column(String(20), nullable=False)  # sheets, lengths, meters, units, panels, boxes, etc.
    yard_id = Column(String(50), ForeignKey("yards.id"), nullable=False)
    location_id = Column(String(50), ForeignKey("storage_locations.id"))
    ship_id = Column(String(50), ForeignKey("ships.id"))
    status = Column(Enum(MaterialStatusEnum), default=MaterialStatusEnum.HEALTHY, nullable=False)

    category = relationship("MaterialCategory", back_populates="materials")
    yard = relationship("Yard", back_populates="materials")
    location = relationship("StorageLocation", back_populates="materials")
    ship = relationship("Ship", back_populates="materials")
    transactions = relationship("MaterialTransaction", back_populates="material")

    def __repr__(self):
        return f"<Material(id={self.id}, name={self.name}, available={self.available})>"
