"""Goods receipts against purchase orders.

A receipt is the only procurement record that changes stock: each accepted quantity is added to a
destination batch with a RECEIPT ledger row in the same transaction. Rejected quantities are recorded
here and on the purchase-order line for reporting, never enter stock, and stay outstanding on the
order so the supplier can redeliver.
"""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class GoodsReceipt(Base, TimestampMixin):
    __tablename__ = "goods_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    yard_id = Column(String(50), ForeignKey("yards.id"), nullable=False)
    location_id = Column(String(50), ForeignKey("storage_locations.id"))
    delivery_note = Column(String(100))
    notes = Column(Text)
    received_by = Column(String(100), nullable=False)
    received_at = Column(DateTime, nullable=False, default=func.now())
    idempotency_key = Column(String(100), nullable=False, unique=True)
    request_fingerprint = Column(String(64), nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="receipts")
    yard = relationship("Yard")
    location = relationship("StorageLocation")
    lines = relationship("GoodsReceiptLine", back_populates="receipt", order_by="GoodsReceiptLine.id")

    @property
    def display_id(self) -> str:
        return f"GR-{self.id:05d}"


class GoodsReceiptLine(Base, TimestampMixin):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        UniqueConstraint("goods_receipt_id", "purchase_order_line_id", name="uq_goods_receipt_lines_receipt_po_line"),
        CheckConstraint("accepted_quantity >= 0", name="ck_goods_receipt_lines_accepted_nonnegative"),
        CheckConstraint("rejected_quantity >= 0", name="ck_goods_receipt_lines_rejected_nonnegative"),
        CheckConstraint("accepted_quantity + rejected_quantity > 0", name="ck_goods_receipt_lines_quantity_positive"),
        CheckConstraint("accepted_quantity = 0 OR destination_material_id IS NOT NULL",
                        name="ck_goods_receipt_lines_accepted_has_destination"),
        CheckConstraint("rejected_quantity = 0 OR rejection_reason IS NOT NULL",
                        name="ck_goods_receipt_lines_rejected_has_reason"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    goods_receipt_id = Column(Integer, ForeignKey("goods_receipts.id"), nullable=False, index=True)
    purchase_order_line_id = Column(Integer, ForeignKey("purchase_order_lines.id"), nullable=False, index=True)
    accepted_quantity = Column(Integer, nullable=False, default=0, server_default="0")
    rejected_quantity = Column(Integer, nullable=False, default=0, server_default="0")
    rejection_reason = Column(Text)
    destination_material_id = Column(String(50), ForeignKey("materials.id"), index=True)

    receipt = relationship("GoodsReceipt", back_populates="lines")
    purchase_order_line = relationship("PurchaseOrderLine")
    destination_material = relationship("Material")
    inspection_hold = relationship("InspectionHold", back_populates="goods_receipt_line", uselist=False)
