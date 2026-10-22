"""Pydantic schemas for inspection holds."""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.inspection import InspectionStatus, RejectionDisposition
from app.models.material import MaterialStatusEnum

Actor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class InspectionCreate(BaseModel):
    """Holds part of a batch's available stock for inspection."""
    actor: Optional[Actor] = Field(None, description="Set by the server from the signed-in user")
    material_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    quantity: int = Field(..., gt=0, description="Available quantity to hold")
    reason: Reason


class InspectionRelease(BaseModel):
    actor: Optional[Actor] = Field(None, description="Set by the server from the signed-in user")
    expected_version: int = Field(..., ge=1)
    quantity: int = Field(..., gt=0, description="Quantity passed and made available")
    note: Optional[Reason] = None


class InspectionReject(BaseModel):
    actor: Optional[Actor] = Field(None, description="Set by the server from the signed-in user")
    expected_version: int = Field(..., ge=1)
    quantity: int = Field(..., gt=0, description="Quantity failed and removed from stock")
    reason: Reason
    disposition: RejectionDisposition


class _Ref(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class _LocationRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    zone: str
    aisle: str


class _MaterialRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    batch: str
    unit: str
    status: MaterialStatusEnum
    quantity: int
    available: int
    yard: _Ref
    location: Optional[_LocationRef]


class _OrderRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_id: str
    supplier: _Ref


class _ReceiptRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_id: str
    delivery_note: Optional[str]
    received_by: str
    received_at: datetime
    purchase_order: _OrderRef


class _OrderLineRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    line_no: int
    description: str


class _ReceiptLineRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    purchase_order_line: _OrderLineRef
    receipt: _ReceiptRef


class InspectionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: str
    from_status: Optional[str]
    to_status: str
    quantity: int
    disposition: Optional[str]
    actor: str
    reason: Optional[str]
    version: int
    created_at: datetime


class InspectionHoldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_id: str
    status: InspectionStatus
    quantity: int
    released_quantity: int
    rejected_quantity: int
    outstanding_quantity: int
    created_by: str
    version: int
    created_at: datetime
    updated_at: datetime
    material: _MaterialRef
    goods_receipt_line: Optional[_ReceiptLineRef]  # None for a hold opened by hand on existing stock


class InspectionHoldDetail(InspectionHoldRead):
    events: list[InspectionEventRead]
