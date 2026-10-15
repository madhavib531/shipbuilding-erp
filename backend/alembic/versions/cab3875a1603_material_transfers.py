"""material transfers

Adds material_transfers and material_transfer_events, a materials.version counter for stale-edit
protection, CHECK constraints on materials stock columns, and TRANSFER_OUT / TRANSFER_IN ledger types.

Upgrade fails (and PostgreSQL rolls the whole revision back) if any existing materials row violates
the new CHECK constraints.

Downgrade limitation: PostgreSQL cannot remove values from an enum type, so TRANSFER_OUT and
TRANSFER_IN stay in the transactiontype enum after downgrading. They are unused by the earlier
schema and harmless, and re-upgrading skips them because of IF NOT EXISTS.

Revision ID: cab3875a1603
Revises: 45e53a0f1df0
Create Date: 2026-10-14 23:53:11.309053

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cab3875a1603'
down_revision: Union[str, Sequence[str], None] = '45e53a0f1df0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MATERIAL_CHECKS = (
    ('ck_materials_quantity_nonnegative', 'quantity >= 0'),
    ('ck_materials_available_nonnegative', 'available >= 0'),
    ('ck_materials_reserved_nonnegative', 'reserved >= 0'),
    ('ck_materials_allocation_within_quantity', 'available + reserved <= quantity'),
)


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_context().dialect.name == 'postgresql':
        # ADD VALUE cannot share a transaction with statements that use the new value.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'TRANSFER_OUT'")
            op.execute("ALTER TYPE transactiontype ADD VALUE IF NOT EXISTS 'TRANSFER_IN'")
    else:
        # Without native enums the column is VARCHAR sized to the longest name; TRANSFER_OUT needs 12.
        with op.batch_alter_table('material_transactions') as batch:
            batch.alter_column('transaction_type', existing_type=sa.String(10), type_=sa.String(12),
                               existing_nullable=False)

    with op.batch_alter_table('materials') as batch:
        batch.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        for name, condition in MATERIAL_CHECKS:
            batch.create_check_constraint(name, condition)

    op.create_table('material_transfers',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('material_id', sa.String(length=50), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('unit', sa.String(length=20), nullable=False),
    sa.Column('from_yard_id', sa.String(length=50), nullable=False),
    sa.Column('from_location_id', sa.String(length=50), nullable=True),
    sa.Column('to_yard_id', sa.String(length=50), nullable=False),
    sa.Column('to_location_id', sa.String(length=50), nullable=True),
    sa.Column('status', sa.Enum('REQUESTED', 'APPROVED', 'REJECTED', 'DISPATCHED', 'RECEIVED', 'CANCELLED', name='transferstatus'), nullable=False),
    sa.Column('expected_arrival', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('requested_by', sa.String(length=100), nullable=False),
    sa.Column('whole_batch', sa.Boolean(), nullable=True),
    sa.Column('received_quantity', sa.Integer(), nullable=True),
    sa.Column('destination_material_id', sa.String(length=50), nullable=True),
    sa.Column('idempotency_key', sa.String(length=100), nullable=True),
    sa.Column('request_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("to_yard_id <> from_yard_id OR COALESCE(to_location_id, '') <> COALESCE(from_location_id, '')", name='ck_material_transfers_route_changes_place'),
    sa.CheckConstraint('quantity > 0', name='ck_material_transfers_quantity_positive'),
    sa.CheckConstraint('received_quantity IS NULL OR (received_quantity >= 0 AND received_quantity <= quantity)', name='ck_material_transfers_received_within_quantity'),
    sa.ForeignKeyConstraint(['destination_material_id'], ['materials.id'], ),
    sa.ForeignKeyConstraint(['from_location_id'], ['storage_locations.id'], ),
    sa.ForeignKeyConstraint(['from_yard_id'], ['yards.id'], ),
    sa.ForeignKeyConstraint(['material_id'], ['materials.id'], ),
    sa.ForeignKeyConstraint(['to_location_id'], ['storage_locations.id'], ),
    sa.ForeignKeyConstraint(['to_yard_id'], ['yards.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key')
    )
    op.create_index(op.f('ix_material_transfers_material_id'), 'material_transfers', ['material_id'], unique=False)
    op.create_index(op.f('ix_material_transfers_status'), 'material_transfers', ['status'], unique=False)
    op.create_index(op.f('ix_material_transfers_to_yard_id'), 'material_transfers', ['to_yard_id'], unique=False)
    op.create_table('material_transfer_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('transfer_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('from_status', sa.String(length=20), nullable=True),
    sa.Column('to_status', sa.String(length=20), nullable=False),
    sa.Column('actor', sa.String(length=100), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['transfer_id'], ['material_transfers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_material_transfer_events_transfer_id'), 'material_transfer_events', ['transfer_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema. Drops all transfer data; ledger enum values remain (see module docstring)."""
    op.drop_index(op.f('ix_material_transfer_events_transfer_id'), table_name='material_transfer_events')
    op.drop_table('material_transfer_events')
    op.drop_index(op.f('ix_material_transfers_to_yard_id'), table_name='material_transfers')
    op.drop_index(op.f('ix_material_transfers_status'), table_name='material_transfers')
    op.drop_index(op.f('ix_material_transfers_material_id'), table_name='material_transfers')
    op.drop_table('material_transfers')
    sa.Enum(name='transferstatus').drop(op.get_bind(), checkfirst=True)

    with op.batch_alter_table('materials') as batch:
        for name, _ in reversed(MATERIAL_CHECKS):
            batch.drop_constraint(name, type_='check')
        batch.drop_column('version')

    if op.get_context().dialect.name != 'postgresql':
        with op.batch_alter_table('material_transactions') as batch:
            batch.alter_column('transaction_type', existing_type=sa.String(12), type_=sa.String(10),
                               existing_nullable=False)
