"""Pydantic schemas for goods receipts."""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

from app.models.inspection import InspectionStatus


def _blank_to_none(value):
    return None if isinstance(value, str) and not value.strip() else value


def _optional_text(max_length: int):
    return Annotated[Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)]],
                     BeforeValidator(_blank_to_none)]


Actor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
EntityId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class GoodsReceiptLineIn(BaseModel):
    purchase_order_line_id: int
    accepted_quantity: int = Field(0, ge=0)
    rejected_quantity: int = Field(0, ge=0)
    rejection_reason: _optional_text(1000) = None
    destination_material_id: Optional[EntityId] = Field(
        None, description="Existing compatible batch at the receiving yard, or a new batch ID")
    batch: _optional_text(50) = Field(None, description="Batch or supplier lot number; required for a new batch")
    hold_for_inspection: bool = Field(
        False, description="Put the accepted quantity on inspection hold in a new batch instead of making it available")

    @model_validator(mode="after")
    def check_quantities(self):
        if self.accepted_quantity + self.rejected_quantity == 0:
            raise ValueError("Each receipt line needs an accepted or rejected quantity")
        if self.rejected_quantity and not self.rejection_reason:
            raise ValueError("rejection_reason is required when goods are rejected")
        if self.accepted_quantity and not self.destination_material_id:
            raise ValueError("destination_material_id is required for accepted goods")
        if self.hold_for_inspection and not self.accepted_quantity:
            raise ValueError("hold_for_inspection needs an accepted quantity to hold")
        return self


class GoodsReceiptCreate(BaseModel):
    actor: Optional[Actor] = Field(None, description="Set by the server from the signed-in user")
    expected_version: int = Field(..., ge=1, description="The purchase order's current version")
    yard_id: EntityId
    location_id: Optional[EntityId] = None
    delivery_note: _optional_text(100) = None
    notes: _optional_text(2000) = None
    lines: list[GoodsReceiptLineIn] = Field(..., min_length=1, max_length=200)


class _Ref(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class _LocationRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    zone: str
    aisle: str


class _OrderLineRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_no: int
    description: str
    unit: str


class _HoldRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_id: str
    status: InspectionStatus
    quantity: int
    outstanding_quantity: int


class GoodsReceiptLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    purchase_order_line: _OrderLineRef
    accepted_quantity: int
    rejected_quantity: int
    rejection_reason: Optional[str]
    destination_material_id: Optional[str]
    inspection_hold: Optional[_HoldRef]


class GoodsReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_id: str
    purchase_order_id: int
    yard: _Ref
    location: Optional[_LocationRef]
    delivery_note: Optional[str]
    notes: Optional[str]
    received_by: str
    received_at: datetime
    lines: list[GoodsReceiptLineRead]
