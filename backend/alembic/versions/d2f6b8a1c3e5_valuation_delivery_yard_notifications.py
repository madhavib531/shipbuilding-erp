"""stock valuation, delivery yard, notifications

* materials.unit_cost / cost_currency: optional cost of one unit, both set or both empty. Existing batches
  start without a cost (not valued). Quantities are not touched.
* purchase_orders.delivery_yard_id: optional yard the goods are expected at. Existing orders have none.
* notifications: stored in-app notifications, one row per recipient, with read and emailed times.

Downgrade drops the three columns and the table, deleting unit costs, delivery yards and notifications.

Revision ID: d2f6b8a1c3e5
Revises: a7c1e5d2f4b8
Create Date: 2026-10-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2f6b8a1c3e5'
down_revision: Union[str, Sequence[str], None] = 'a7c1e5d2f4b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('materials') as batch:
        batch.add_column(sa.Column('unit_cost', sa.Numeric(14, 4), nullable=True))
        batch.add_column(sa.Column('cost_currency', sa.String(length=3), nullable=True))
        batch.create_check_constraint('ck_materials_unit_cost_nonnegative', 'unit_cost IS NULL OR unit_cost >= 0')
        batch.create_check_constraint('ck_materials_cost_has_currency', '(unit_cost IS NULL) = (cost_currency IS NULL)')
    with op.batch_alter_table('purchase_orders') as batch:
        batch.add_column(sa.Column('delivery_yard_id', sa.String(length=50), nullable=True))
        batch.create_foreign_key('fk_purchase_orders_delivery_yard_id_yards', 'yards', ['delivery_yard_id'], ['id'])
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('page', sa.String(length=40), nullable=True),
    sa.Column('record', sa.String(length=50), nullable=True),
    sa.Column('dedupe_key', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.Column('emailed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'dedupe_key', name='uq_notifications_user_dedupe')
    )
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'read_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_table('notifications')
    with op.batch_alter_table('purchase_orders') as batch:
        batch.drop_constraint('fk_purchase_orders_delivery_yard_id_yards', type_='foreignkey')
        batch.drop_column('delivery_yard_id')
    with op.batch_alter_table('materials') as batch:
        batch.drop_constraint('ck_materials_cost_has_currency', type_='check')
        batch.drop_constraint('ck_materials_unit_cost_nonnegative', type_='check')
        batch.drop_column('cost_currency')
        batch.drop_column('unit_cost')
