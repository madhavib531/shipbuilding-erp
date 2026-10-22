"""Purchase orders, their lines and audit history.

Purchase orders never change stock: only goods receipts (a later milestone) do. Per line,
outstanding = ordered - received - cancelled. Rejected quantities are recorded for reporting but
stay outstanding so the supplier can redeliver.
"""

from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON, CheckConstraint, Column, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class PurchaseOrderStatus(str, PyEnum):
    """DRAFT -> APPROVED -> PARTIALLY_RECEIVED -> RECEIVED. DRAFT and APPROVED may be CANCELLED,
    APPROVED may be reopened to DRAFT before any receipt, PARTIALLY_RECEIVED may be CLOSED.
    RECEIVED, CANCELLED and CLOSED are final."""
    DRAFT = "Draft"
    APPROVED = "Approved"
    PARTIALLY_RECEIVED = "Partially received"
    RECEIVED = "Received"
    CANCELLED = "Cancelled"
    CLOSED = "Closed"


# Approved orders that can still receive goods.
OPEN_PURCHASE_ORDER_STATUSES = (PurchaseOrderStatus.APPROVED, PurchaseOrderStatus.PARTIALLY_RECEIVED)


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_purchase_orders_version_positive"),
        # Anything past approval must carry who approved it, when, and the expected delivery date.
        CheckConstraint(
            "status NOT IN ('APPROVED', 'PARTIALLY_RECEIVED', 'RECEIVED', 'CLOSED') "
            "OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND expected_delivery_date IS NOT NULL)",
            name="ck_purchase_orders_approval_complete",
        ),
        Index("ix_purchase_orders_status_expected_delivery_date", "status", "expected_delivery_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_id = Column(String(50), ForeignKey("suppliers.id"), nullable=False, index=True)
    status = Column(Enum(PurchaseOrderStatus), nullable=False, default=PurchaseOrderStatus.DRAFT)
    expected_delivery_date = Column(Date)
    # Where the goods are expected; receipts default to it and orders can be filtered by it. Optional.
    delivery_yard_id = Column(String(50), ForeignKey("yards.id"))
    notes = Column(Text)
    created_by = Column(String(100), nullable=False)
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    version = Column(Integer, default=1, server_default="1", nullable=False)
    idempotency_key = Column(String(100), unique=True)
    request_fingerprint = Column(String(64))

    supplier = relationship("Supplier")
    delivery_yard = relationship("Yard")
    lines = relationship("PurchaseOrderLine", back_populates="purchase_order", order_by="PurchaseOrderLine.line_no")
    events = relationship("PurchaseOrderEvent", back_populates="purchase_order", order_by="PurchaseOrderEvent.id")
    receipts = relationship("GoodsReceipt", back_populates="purchase_order", order_by="GoodsReceipt.id")

    @property
    def display_id(self) -> str:
        return f"PO-{self.id:05d}"

    @property
    def currency(self) -> str | None:
        """All lines share one currency (enforced when lines are written); None for an empty draft."""
        return self.lines[0].currency if self.lines else None

    @property
    def total_value(self) -> Decimal:
        return sum((l.line_total for l in self.lines), Decimal("0"))

    @property
    def outstanding_value(self) -> Decimal:
        return sum((l.outstanding_quantity * l.unit_price for l in self.lines), Decimal("0"))

    @property
    def ordered_quantity(self) -> int:
        return sum(l.ordered_quantity for l in self.lines)

    @property
    def received_quantity(self) -> int:
        return sum(l.received_quantity for l in self.lines)

    @property
    def is_overdue(self) -> bool:
        return (
            self.status in OPEN_PURCHASE_ORDER_STATUSES
            and self.expected_delivery_date is not None
            and self.expected_delivery_date < date.today()
            and any(l.outstanding_quantity > 0 for l in self.lines)
        )


class PurchaseOrderLine(Base, TimestampMixin):
    """One ordered material, identified by description (category, description, unit, supplier part
    number). Line IDs are stable so goods receipts can reference them."""
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "line_no", name="uq_purchase_order_lines_order_line_no"),
        CheckConstraint("line_no >= 1", name="ck_purchase_order_lines_line_no_positive"),
        CheckConstraint("ordered_quantity > 0", name="ck_purchase_order_lines_ordered_positive"),
        CheckConstraint("received_quantity >= 0", name="ck_purchase_order_lines_received_nonnegative"),
        CheckConstraint("rejected_quantity >= 0", name="ck_purchase_order_lines_rejected_nonnegative"),
        CheckConstraint("cancelled_quantity >= 0", name="ck_purchase_order_lines_cancelled_nonnegative"),
        CheckConstraint(
            "received_quantity + cancelled_quantity <= ordered_quantity",
            name="ck_purchase_order_lines_outstanding_nonnegative",
        ),
        CheckConstraint("unit_price >= 0", name="ck_purchase_order_lines_unit_price_nonnegative"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_purchase_order_lines_currency_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    line_no = Column(Integer, nullable=False)
    category_id = Column(String(50), ForeignKey("material_categories.id"), nullable=False)
    description = Column(String(200), nullable=False)
    unit = Column(String(20), nullable=False)
    supplier_part_number = Column(String(100))
    ordered_quantity = Column(Integer, nullable=False)
    received_quantity = Column(Integer, default=0, server_default="0", nullable=False)
    rejected_quantity = Column(Integer, default=0, server_default="0", nullable=False)
    cancelled_quantity = Column(Integer, default=0, server_default="0", nullable=False)
    unit_price = Column(Numeric(14, 4), nullable=False)
    currency = Column(String(3), nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="lines")
    category = relationship("MaterialCategory")

    @property
    def outstanding_quantity(self) -> int:
        return self.ordered_quantity - self.received_quantity - self.cancelled_quantity

    @property
    def line_total(self) -> Decimal:
        return self.ordered_quantity * self.unit_price


class PurchaseOrderEvent(Base, TimestampMixin):
    """Append-only audit record of one action on a purchase order."""
    __tablename__ = "purchase_order_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    action = Column(String(20), nullable=False)
    from_status = Column(String(20))
    to_status = Column(String(20), nullable=False)
    actor = Column(String(100), nullable=False)
    reason = Column(Text)
    version = Column(Integer, nullable=False)
    changes = Column(JSON)

    purchase_order = relationship("PurchaseOrder", back_populates="events")
