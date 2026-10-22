"""manual inspection holds

Makes inspection_holds.goods_receipt_line_id nullable so a hold can be opened on stock already in a
batch, not only on goods being received. Such a hold has no receipt line. Its unique constraint is
kept: receipt lines still have at most one hold, and NULLs do not collide.

No data changes. Downgrade refuses while any hold without a receipt line exists, because the column
cannot become NOT NULL again; decide and delete those holds by hand first if a downgrade is required.

Revision ID: 9d4c2a7e1b30
Revises: f3263eb479ec
Create Date: 2026-10-21 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d4c2a7e1b30'
down_revision: Union[str, Sequence[str], None] = 'f3263eb479ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('inspection_holds') as batch:
        batch.alter_column('goods_receipt_line_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    manual = op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM inspection_holds WHERE goods_receipt_line_id IS NULL"))
    if manual:
        raise RuntimeError(f"{manual} inspection hold(s) have no goods receipt line; the column cannot be made NOT NULL")
    with op.batch_alter_table('inspection_holds') as batch:
        batch.alter_column('goods_receipt_line_id', existing_type=sa.Integer(), nullable=False)
