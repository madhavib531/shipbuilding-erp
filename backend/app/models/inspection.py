"""Inspection holds on received goods and their audit history.

A hold keeps part of a batch's on-hand quantity out of `available` until an inspector releases it
(it becomes available) or rejects it (it leaves stock as a return to the supplier or as scrap). Held
stock is part of the batch's blocked quantity (quantity - available - reserved), so every path that
allocates or moves stock through `available` excludes it without further checks.

The material row lock guards hold quantities: holds are created and decided only while their batch is
locked, so a reader holding that lock sees a stable held total.
"""

from enum import Enum as PyEnum

from sqlalchemy import CheckConstraint, Column, Enum, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import column_property, relationship

from app.models.base import Base, TimestampMixin
from app.models.material import Material


class InspectionStatus(str, PyEnum):
    """OPEN while any quantity awaits a decision; the other values describe how it was closed."""
    OPEN = "Open"
    RELEASED = "Released"
    REJECTED = "Rejected"
    PARTIALLY_RELEASED = "Partially released"


class RejectionDisposition(str, PyEnum):
    """What happens to rejected goods. Both remove them from on-hand stock."""
    RETURN_TO_SUPPLIER = "Return to supplier"
    SCRAP = "Scrap"


class InspectionHold(Base, TimestampMixin):
    __tablename__ = "inspection_holds"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inspection_holds_quantity_positive"),
        CheckConstraint("released_quantity >= 0", name="ck_inspection_holds_released_nonnegative"),
        CheckConstraint("rejected_quantity >= 0", name="ck_inspection_holds_rejected_nonnegative"),
        CheckConstraint("released_quantity + rejected_quantity <= quantity", name="ck_inspection_holds_decided_within_quantity"),
        CheckConstraint(
            "(status = 'OPEN' AND released_quantity + rejected_quantity < quantity) OR "
            "(status <> 'OPEN' AND released_quantity + rejected_quantity = quantity)",
            name="ck_inspection_holds_status_matches_quantities",
        ),
        CheckConstraint("version >= 1", name="ck_inspection_holds_version_positive"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(String(50), ForeignKey("materials.id"), nullable=False, index=True)
    goods_receipt_line_id = Column(Integer, ForeignKey("goods_receipt_lines.id"), nullable=False, unique=True)
    quantity = Column(Integer, nullable=False)
    released_quantity = Column(Integer, nullable=False, default=0, server_default="0")
    rejected_quantity = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(Enum(InspectionStatus), nullable=False, default=InspectionStatus.OPEN, index=True)
    created_by = Column(String(100), nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")

    material = relationship("Material")
    goods_receipt_line = relationship("GoodsReceiptLine", back_populates="inspection_hold")
    events = relationship("InspectionEvent", back_populates="hold", order_by="InspectionEvent.id")

    @property
    def display_id(self) -> str:
        return f"QI-{self.id:05d}"

    @property
    def outstanding_quantity(self) -> int:
        return self.quantity - self.released_quantity - self.rejected_quantity


class InspectionEvent(Base, TimestampMixin):
    """Append-only audit record of one action on an inspection hold."""
    __tablename__ = "inspection_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hold_id = Column(Integer, ForeignKey("inspection_holds.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # held, released, rejected
    from_status = Column(String(20))
    to_status = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False)
    disposition = Column(String(30))
    actor = Column(String(100), nullable=False)
    reason = Column(Text)
    version = Column(Integer, nullable=False)

    hold = relationship("InspectionHold", back_populates="events")


# Quantity of the batch still awaiting an inspection decision. Deferred so it stays out of the
# SELECT ... FOR UPDATE queries that lock materials; list queries undefer it explicitly.
Material.held_quantity = column_property(
    select(func.coalesce(func.sum(
        InspectionHold.quantity - InspectionHold.released_quantity - InspectionHold.rejected_quantity), 0))
    .where(InspectionHold.material_id == Material.id)
    .correlate_except(InspectionHold)
    .scalar_subquery(),
    deferred=True,
)
