"""Material Pydantic schemas for validation and serialization."""

from pydantic import BaseModel, BeforeValidator, Field, StringConstraints, model_validator
from typing import Annotated, Optional, List
from datetime import datetime
from app.models.material import MaterialStatusEnum
from app.models.transaction import TransactionType


def _blank_to_none(value):
    return None if isinstance(value, str) and not value.strip() else value


# Blank strings become None so a whitespace-only reason or actor counts as missing.
StockActor = Annotated[Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]],
                       BeforeValidator(_blank_to_none)]
StockReason = Annotated[Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]],
                        BeforeValidator(_blank_to_none)]


class MaterialCategoryBase(BaseModel):
    """Base schema for material categories."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class MaterialCategoryCreate(MaterialCategoryBase):
    """Schema for creating material categories."""
    id: str = Field(..., min_length=1, max_length=50)


class MaterialCategoryRead(MaterialCategoryBase):
    """Schema for reading material categories."""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MaterialBase(BaseModel):
    """Base schema for materials."""
    name: str = Field(..., min_length=1, max_length=200)
    category_id: str = Field(..., min_length=1, max_length=50)
    batch: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., ge=0)
    available: int = Field(..., ge=0)
    reserved: int = Field(..., ge=0)
    unit: str = Field(..., min_length=1, max_length=20)
    yard_id: str = Field(..., min_length=1, max_length=50)
    location_id: Optional[str] = Field(None, max_length=50)
    ship_id: Optional[str] = Field(None, max_length=50)
    status: MaterialStatusEnum = MaterialStatusEnum.HEALTHY

    @model_validator(mode="after")
    def validate_quantities(self):
        """Ensure available and reserved don't exceed total quantity."""
        if self.available + self.reserved > self.quantity:
            raise ValueError(
                f"available ({self.available}) + reserved ({self.reserved}) "
                f"cannot exceed quantity ({self.quantity})"
            )
        return self


class MaterialCreate(MaterialBase):
    """Schema for creating materials. A batch created with stock records an opening-balance ADJUSTMENT,
    so `actor` is required whenever quantity is above zero; `stock_reason` is an optional note."""
    id: str = Field(..., min_length=1, max_length=50)
    actor: StockActor = None
    stock_reason: StockReason = None


class MaterialUpdate(BaseModel):
    """Schema for updating materials (partial updates allowed)."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category_id: Optional[str] = Field(None, min_length=1, max_length=50)
    batch: Optional[str] = Field(None, min_length=1, max_length=50)
    quantity: Optional[int] = Field(None, ge=0)
    available: Optional[int] = Field(None, ge=0)
    reserved: Optional[int] = Field(None, ge=0)
    unit: Optional[str] = Field(None, min_length=1, max_length=20)
    yard_id: Optional[str] = Field(None, min_length=1, max_length=50)
    location_id: Optional[str] = Field(None, max_length=50)
    ship_id: Optional[str] = Field(None, max_length=50)
    status: Optional[MaterialStatusEnum] = None
    expected_version: Optional[int] = Field(
        None, ge=1, description="The version the client last read; the update is refused with 409 if it changed"
    )
    actor: StockActor = Field(None, description="Required when quantity, available or reserved changes")
    stock_reason: StockReason = Field(None, description="Required when quantity, available or reserved changes")

    # Cross-field quantity rules need the stored values, so the endpoint checks them after merging.
    @model_validator(mode="after")
    def reject_null_for_required_fields(self):
        nullable = {"location_id", "ship_id", "expected_version", "actor", "stock_reason"}
        nulled = sorted(f for f in self.model_fields_set - nullable if getattr(self, f) is None)
        if nulled:
            raise ValueError(f"These fields cannot be null: {', '.join(nulled)}")
        return self


class MaterialRead(MaterialBase):
    """Schema for reading materials."""
    id: str
    version: int
    held_quantity: int = Field(0, description="Part of the blocked quantity on inspection hold")
    created_at: datetime
    updated_at: datetime
    category: MaterialCategoryRead
    yard: "YardRead"
    location: Optional["StorageLocationRead"] = None
    ship: Optional["ShipRead"] = None

    class Config:
        from_attributes = True


class MaterialTransactionRead(BaseModel):
    """One ledger row: a stock movement or status change of a batch."""
    id: str
    transaction_type: TransactionType
    quantity: int
    unit: str
    from_location_id: Optional[str]
    to_location_id: Optional[str]
    reference_id: Optional[str]
    actor: str
    reason: Optional[str]
    status: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class MaterialListResponse(BaseModel):
    """Schema for material list response."""
    materials: List[MaterialRead]
    total: int
    skip: int
    limit: int


# Forward references for related entities
class YardRead(BaseModel):
    """Schema for reading yards."""
    id: str
    name: str

    class Config:
        from_attributes = True


class StorageLocationRead(BaseModel):
    """Schema for reading storage locations."""
    id: str
    zone: str
    aisle: str

    class Config:
        from_attributes = True


class ShipRead(BaseModel):
    """Schema for reading ships."""
    id: str
    name: str

    class Config:
        from_attributes = True


# Update forward references
MaterialRead.model_rebuild()
