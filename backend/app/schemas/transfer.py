"""Pydantic schemas for material transfers."""

from datetime import date, datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.transfer import TransferStatus

Actor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
EntityId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class TransferCreate(BaseModel):
    material_id: EntityId
    quantity: int = Field(..., gt=0)
    to_yard_id: EntityId
    to_location_id: Optional[EntityId] = None
    expected_arrival: Optional[date] = None
    notes: Optional[Reason] = None
    actor: Actor


class TransferNote(BaseModel):
    """Approve or dispatch; the note is optional."""
    actor: Actor
    reason: Optional[Reason] = None


class TransferReason(BaseModel):
    """Reject or cancel; a reason is required."""
    actor: Actor
    reason: Reason


class TransferReceive(BaseModel):
    actor: Actor
    received_quantity: Optional[int] = Field(None, ge=0, description="Defaults to the dispatched quantity")
    destination_material_id: Optional[EntityId] = Field(
        None,
        description="Existing compatible batch at the destination, or a new batch ID. "
                    "Omit only for a whole-batch relocation.",
    )
    discrepancy_reason: Optional[Reason] = None


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


class TransferEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: str
    from_status: Optional[str]
    to_status: str
    actor: str
    reason: Optional[str]
    quantity: Optional[int]
    created_at: datetime


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_id: str
    material_id: str
    material: _MaterialRef
    quantity: int
    unit: str
    from_yard: _Ref
    from_location: Optional[_LocationRef]
    to_yard: _Ref
    to_location: Optional[_LocationRef]
    status: TransferStatus
    expected_arrival: Optional[date]
    notes: Optional[str]
    requested_by: str
    received_quantity: Optional[int]
    shortage_quantity: Optional[int]
    destination_material_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    events: list[TransferEventRead]
