"""Pydantic schemas for purchase orders."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

from app.models.purchase_order import PurchaseOrderStatus
from app.models.supplier import SupplierStatusEnum
from app.schemas.goods_receipt import GoodsReceiptRead


def _blank_to_none(value):
    return None if isinstance(value, str) and not value.strip() else value


Actor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
EntityId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Notes = Annotated[Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]],
                  BeforeValidator(_blank_to_none)]
PartNumber = Annotated[Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]],
                       BeforeValidator(_blank_to_none)]
# Exactly four fractional digits at most; anything finer is rejected rather than rounded.
UnitPrice = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class PurchaseOrderLineIn(BaseModel):
    category_id: EntityId
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
    supplier_part_number: PartNumber = None
    ordered_quantity: int = Field(..., gt=0)
    unit_price: UnitPrice
    currency: Currency


class PurchaseOrderCreate(BaseModel):
    actor: Actor
    supplier_id: EntityId
    expected_delivery_date: Optional[date] = None
    notes: Notes = None
    lines: list[PurchaseOrderLineIn] = Field(default_factory=list, max_length=200)


class PurchaseOrderUpdate(BaseModel):
    """Draft edit. `lines`, when sent, replaces every line of the draft."""
    actor: Actor
    expected_version: int = Field(..., ge=1)
    supplier_id: Optional[EntityId] = None
    expected_delivery_date: Optional[date] = None
    notes: Notes = None
    lines: Optional[list[PurchaseOrderLineIn]] = Field(None, max_length=200)

    @model_validator(mode="after")
    def reject_null_for_required_fields(self):
        nulled = sorted(f for f in {"supplier_id", "lines"} & self.model_fields_set if getattr(self, f) is None)
        if nulled:
            raise ValueError(f"These fields cannot be null: {', '.join(nulled)}")
        return self


class PurchaseOrderAction(BaseModel):
    """Approve: the note is optional."""
    actor: Actor
    expected_version: int = Field(..., ge=1)
    reason: Optional[Reason] = None


class PurchaseOrderReasonAction(BaseModel):
    """Reopen, cancel and close: a reason is required."""
    actor: Actor
    expected_version: int = Field(..., ge=1)
    reason: Reason


class _SupplierRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    status: SupplierStatusEnum


class _CategoryRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class PurchaseOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_no: int
    category: _CategoryRef
    description: str
    unit: str
    supplier_part_number: Optional[str]
    ordered_quantity: int
    received_quantity: int
    rejected_quantity: int
    cancelled_quantity: int
    outstanding_quantity: int
    unit_price: Decimal
    currency: str
    line_total: Decimal


class PurchaseOrderEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: str
    from_status: Optional[str]
    to_status: str
    actor: str
    reason: Optional[str]
    version: int
    changes: Optional[dict]
    created_at: datetime


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_id: str
    supplier: _SupplierRef
    status: PurchaseOrderStatus
    expected_delivery_date: Optional[date]
    notes: Optional[str]
    created_by: str
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    version: int
    currency: Optional[str]
    total_value: Decimal
    outstanding_value: Decimal
    ordered_quantity: int
    received_quantity: int
    is_overdue: bool
    created_at: datetime
    updated_at: datetime
    lines: list[PurchaseOrderLineRead]


class PurchaseOrderDetail(PurchaseOrderRead):
    events: list[PurchaseOrderEventRead]
    receipts: list[GoodsReceiptRead]
