"""Pydantic schemas for suppliers."""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator

from app.models.supplier import SupplierStatusEnum


def _blank_to_none(value):
    return None if isinstance(value, str) and not value.strip() else value


def _optional_text(max_length: int, pattern: str | None = None):
    return Annotated[
        Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length, pattern=pattern)]],
        BeforeValidator(_blank_to_none),
    ]


SupplierId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
SupplierName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
ContactPerson = _optional_text(100)
ContactEmail = _optional_text(100, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ContactPhone = _optional_text(20)
Address = _optional_text(300)
Country = _optional_text(50)
Notes = _optional_text(500)


class SupplierCreate(BaseModel):
    id: SupplierId
    name: SupplierName
    contact_person: ContactPerson = None
    contact_email: ContactEmail = None
    contact_phone: ContactPhone = None
    address: Address = None
    country: Country = None
    status: SupplierStatusEnum = SupplierStatusEnum.APPROVED
    notes: Notes = None


class SupplierUpdate(BaseModel):
    """Partial update; send null or an empty string to clear an optional field."""
    name: Optional[SupplierName] = None
    contact_person: ContactPerson = None
    contact_email: ContactEmail = None
    contact_phone: ContactPhone = None
    address: Address = None
    country: Country = None
    status: Optional[SupplierStatusEnum] = None
    notes: Notes = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self):
        nulled = sorted(f for f in {"name", "status"} & self.model_fields_set if getattr(self, f) is None)
        if nulled:
            raise ValueError(f"These fields cannot be null: {', '.join(nulled)}")
        return self


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    contact_person: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    address: Optional[str]
    country: Optional[str]
    status: SupplierStatusEnum
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
