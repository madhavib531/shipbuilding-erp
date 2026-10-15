"""Material transaction and movement tracking."""

from sqlalchemy import Column, String, Integer, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from app.models.base import Base, TimestampMixin


class TransactionType(str, PyEnum):
    """Type of material transaction."""
    RECEIPT = "Receipt"
    ISSUANCE = "Issuance"
    TRANSFER = "Transfer"
    TRANSFER_OUT = "Transfer out"
    TRANSFER_IN = "Transfer in"
    ADJUSTMENT = "Adjustment"
    RETURN = "Return"
    SCRAP = "Scrap"
    INSPECTION = "Inspection"
    QUARANTINE = "Quarantine"
    RELEASE = "Release"


class MaterialTransaction(Base, TimestampMixin):
    """Log of all material movements and transactions."""
    __tablename__ = "material_transactions"

    id = Column(String(50), primary_key=True)
    material_id = Column(String(50), ForeignKey("materials.id"), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit = Column(String(20), nullable=False)
    from_location_id = Column(String(50), ForeignKey("storage_locations.id"))
    to_location_id = Column(String(50), ForeignKey("storage_locations.id"))
    from_ship_id = Column(String(50), ForeignKey("ships.id"))
    to_ship_id = Column(String(50), ForeignKey("ships.id"))
    reference_id = Column(String(50))  # PO, Receipt, Transfer ID, etc.
    actor = Column(String(100), nullable=False)  # Username or user ID who performed action
    reason = Column(Text)
    status = Column(String(50), default="Completed")  # Completed, Pending, Cancelled, etc.

    material = relationship("Material", back_populates="transactions")

    def __repr__(self):
        return f"<MaterialTransaction(id={self.id}, type={self.transaction_type}, qty={self.quantity})>"
