"""exchange rates

Adds `exchange_rates`: one row per foreign currency with its value in the base currency (INR), entered by an
admin. Used only to convert totals for display; stored costs and prices keep their own currency. No existing
table changes. Downgrade drops the table and the rates in it.

Revision ID: e8b3c1f4a9d2
Revises: d2f6b8a1c3e5
Create Date: 2026-10-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8b3c1f4a9d2'
down_revision: Union[str, Sequence[str], None] = 'd2f6b8a1c3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('exchange_rates',
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('rate', sa.Numeric(18, 6), nullable=False),
    sa.Column('updated_by', sa.String(length=100), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('rate > 0', name='ck_exchange_rates_rate_positive'),
    sa.CheckConstraint('length(currency) = 3 AND currency = upper(currency)', name='ck_exchange_rates_currency_code'),
    sa.PrimaryKeyConstraint('currency')
    )


def downgrade() -> None:
    op.drop_table('exchange_rates')
