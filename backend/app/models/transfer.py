"""Material transfers between yards/locations and their audit history."""

from enum import Enum as PyEnum

from sqlalchemy import Boolean, CheckConstraint, Column, Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class TransferStatus(str, PyEnum):
    """Transfer lifecycle: REQUESTED -> APPROVED -> DISPATCHED -> RECEIVED.

    REQUESTED may be REJECTED or CANCELLED; APPROVED may be CANCELLED. Final states are
    RECEIVED, REJECTED and CANCELLED. Stock leaves the source batch only at DISPATCHED.
    """
    REQUESTED = "Requested"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    DISPATCHED = "Dispatched"
    RECEIVED = "Received"
    CANCELLED = "Cancelled"


# Transfers still awaiting an action; RECEIVED, REJECTED and CANCELLED are final.
PENDING_TRANSFER_STATUSES = (TransferStatus.REQUESTED, TransferStatus.APPROVED, TransferStatus.DISPATCHED)


class MaterialTransfer(Base, TimestampMixin):
    """Movement of stock from one batch to a destination yard and optional location."""
    __tablename__ = "material_transfers"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_material_transfers_quantity_positive"),
        CheckConstraint(
            "received_quantity IS NULL OR (received_quantity >= 0 AND received_quantity <= quantity)",
            name="ck_material_transfers_received_within_quantity",
        ),
        CheckConstraint(
            "to_yard_id <> from_yard_id OR COALESCE(to_location_id, '') <> COALESCE(from_location_id, '')",
            name="ck_material_transfers_route_changes_place",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(String(50), ForeignKey("materials.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit = Column(String(20), nullable=False)
    from_yard_id = Column(String(50), ForeignKey("yards.id"), nullable=False)
    from_location_id = Column(String(50), ForeignKey("storage_locations.id"))
    to_yard_id = Column(String(50), ForeignKey("yards.id"), nullable=False, index=True)
    to_location_id = Column(String(50), ForeignKey("storage_locations.id"))
    status = Column(Enum(TransferStatus), nullable=False, default=TransferStatus.REQUESTED, index=True)
    expected_arrival = Column(Date)
    notes = Column(Text)
    requested_by = Column(String(100), nullable=False)
    # Set at dispatch: True when this transfer took the batch's entire on-hand quantity.
    whole_batch = Column(Boolean)
    received_quantity = Column(Integer)
    destination_material_id = Column(String(50), ForeignKey("materials.id"))
    idempotency_key = Column(String(100), unique=True)
    request_fingerprint = Column(String(64))

    material = relationship("Material", foreign_keys=[material_id])
    destination_material = relationship("Material", foreign_keys=[destination_material_id])
    from_yard = relationship("Yard", foreign_keys=[from_yard_id])
    to_yard = relationship("Yard", foreign_keys=[to_yard_id])
    from_location = relationship("StorageLocation", foreign_keys=[from_location_id])
    to_location = relationship("StorageLocation", foreign_keys=[to_location_id])
    events = relationship(
        "MaterialTransferEvent", back_populates="transfer", order_by="MaterialTransferEvent.id"
    )

    @property
    def display_id(self) -> str:
        return f"TR-{self.id:05d}"

    @property
    def shortage_quantity(self) -> int | None:
        if self.received_quantity is None:
            return None
        return self.quantity - self.received_quantity


class MaterialTransferEvent(Base, TimestampMixin):
    """Append-only audit record of one lifecycle action on a transfer."""
    __tablename__ = "material_transfer_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transfer_id = Column(Integer, ForeignKey("material_transfers.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False)
    from_status = Column(String(20))
    to_status = Column(String(20), nullable=False)
    actor = Column(String(100), nullable=False)
    reason = Column(Text)
    quantity = Column(Integer)

    transfer = relationship("MaterialTransfer", back_populates="events")
