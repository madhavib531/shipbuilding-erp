"""users and sessions

Adds `users` (accounts with a role and an scrypt password hash) and `user_sessions` (bearer-token sessions,
stored as SHA-256 digests) plus the `userrole` enum. No existing table changes. After upgrading, create the
first admin with `python scripts/create_user.py`; until then nobody can sign in.

Downgrade drops both tables and the enum, deleting all accounts and sessions.

Revision ID: a7c1e5d2f4b8
Revises: 9d4c2a7e1b30
Create Date: 2026-10-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c1e5d2f4b8'
down_revision: Union[str, Sequence[str], None] = '9d4c2a7e1b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('role', sa.Enum('ADMIN', 'STOREKEEPER', 'PROCUREMENT', 'INSPECTOR', 'VIEWER', name='userrole'), nullable=False),
    sa.Column('password_hash', sa.String(length=300), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('user_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
