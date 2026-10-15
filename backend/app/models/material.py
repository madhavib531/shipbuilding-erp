"""Material and MaterialCategory models."""

from sqlalchemy import CheckConstraint, Column, String, Integer, Float, ForeignKey, Enum
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
    """A batch of material held at one yard.

    quantity is on hand at the yard; available is free to issue or transfer; reserved is held
    for a ship; quantity - available - reserved is blocked (e.g. inspection or quarantine).
    Stock in transit is not counted here; it lives on dispatched MaterialTransfer rows.
    """
    __tablename__ = "materials"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_materials_quantity_nonnegative"),
        CheckConstraint("available >= 0", name="ck_materials_available_nonnegative"),
        CheckConstraint("reserved >= 0", name="ck_materials_reserved_nonnegative"),
        CheckConstraint("available + reserved <= quantity", name="ck_materials_allocation_within_quantity"),
    )

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
    # Incremented on every stock or attribute change; clients send it back to detect stale edits.
    version = Column(Integer, default=1, server_default="1", nullable=False)

    category = relationship("MaterialCategory", back_populates="materials")
    yard = relationship("Yard", back_populates="materials")
    location = relationship("StorageLocation", back_populates="materials")
    ship = relationship("Ship", back_populates="materials")
    transactions = relationship("MaterialTransaction", back_populates="material")

    def __repr__(self):
        return f"<Material(id={self.id}, name={self.name}, available={self.available})>"
