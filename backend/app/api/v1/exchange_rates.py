"""Exchange rates into the base currency (INR). Everyone can read them; admins set them."""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import require
from app.database import get_db
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.services import currency_service as service

router = APIRouter(prefix="/api/v1/exchange-rates", tags=["exchange rates"])


class RateIn(BaseModel):
    rate: Decimal = Field(..., gt=0, max_digits=18, decimal_places=6, description="Value of 1 unit in the base currency")


class RateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    currency: str
    rate: Decimal
    updated_by: str
    updated_at: datetime


def _payload(db: Session) -> dict:
    return {"base": service.base(), "rates": [RateRead.model_validate(r).model_dump(mode="json") for r in service.list_rates(db)]}


@router.get("", response_model=SuccessResponse)
def list_rates(db: Session = Depends(get_db)):
    return SuccessResponse(message="Exchange rates", data=_payload(db))


@router.put("/{currency}", response_model=SuccessResponse)
def set_rate(currency: str, data: RateIn, user: User = Depends(require("users")), db: Session = Depends(get_db)):
    service.set_rate(db, currency, data.rate, user.display_name)
    return SuccessResponse(message="Exchange rate saved", data=_payload(db))


@router.delete("/{currency}", response_model=SuccessResponse)
def delete_rate(currency: str, _: User = Depends(require("users")), db: Session = Depends(get_db)):
    service.delete_rate(db, currency)
    return SuccessResponse(message="Exchange rate removed", data=_payload(db))
