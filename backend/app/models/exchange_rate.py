"""Exchange rates into the base currency (INR), entered by an admin. One row per foreign currency."""

from sqlalchemy import CheckConstraint, Column, DateTime, Numeric, String

from app.models.base import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        CheckConstraint("rate > 0", name="ck_exchange_rates_rate_positive"),
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_exchange_rates_currency_code"),
    )

    currency = Column(String(3), primary_key=True)    # e.g. USD
    rate = Column(Numeric(18, 6), nullable=False)      # value of 1 unit of `currency` in the base currency
    updated_by = Column(String(100), nullable=False)
    updated_at = Column(DateTime, nullable=False)
