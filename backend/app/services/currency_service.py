"""Converting per-currency totals into the base currency (INR) with admin-entered exchange rates.

Stored costs and prices always keep their own currency; conversion happens only when totals are shown. A
currency without a rate is never guessed: its amount is reported under `missing_rates` instead.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import InvalidInputError, ItemNotFoundError
from app.models.exchange_rate import ExchangeRate

CENT = Decimal("0.01")


def base() -> str:
    return settings.base_currency.upper()


def rates(db: Session) -> dict[str, Decimal]:
    found = {r.currency: Decimal(r.rate) for r in db.scalars(select(ExchangeRate))}
    found[base()] = Decimal(1)
    return found


def to_base(db: Session, amounts: list[dict]) -> dict:
    """`amounts` is [{"currency", "amount"}]; returns the total in the base currency and how it was made."""
    known = rates(db)
    total = Decimal(0)
    parts, missing = [], []
    for item in amounts:
        currency, amount = item["currency"], Decimal(str(item["amount"]))
        rate = known.get(currency)
        if rate is None:
            missing.append({"currency": currency, "amount": str(amount.quantize(CENT))})
            continue
        converted = amount * rate
        total += converted
        parts.append({"currency": currency, "amount": str(amount.quantize(CENT)), "rate": str(rate.normalize()),
                      "in_base": str(converted.quantize(CENT))})
    return {"currency": base(), "amount": str(total.quantize(CENT)), "parts": parts, "missing_rates": missing}


def list_rates(db: Session) -> list[ExchangeRate]:
    return db.scalars(select(ExchangeRate).order_by(ExchangeRate.currency)).all()


def set_rate(db: Session, currency: str, rate: Decimal, actor: str) -> ExchangeRate:
    currency = currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise InvalidInputError("Currency must be a 3-letter code such as USD")
    if currency == base():
        raise InvalidInputError(f"{base()} is the base currency; its rate is always 1")
    row = db.get(ExchangeRate, currency) or ExchangeRate(currency=currency)
    row.rate, row.updated_by, row.updated_at = rate, actor, datetime.now()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_rate(db: Session, currency: str) -> None:
    row = db.get(ExchangeRate, currency.strip().upper())
    if row is None:
        raise ItemNotFoundError("Exchange rate", currency)
    db.delete(row)
    db.commit()
