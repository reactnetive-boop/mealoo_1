"""users constraints and indexes

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-06-16 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a1b2'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK: at least one contact method must be present
    op.create_check_constraint(
        'chk_users_contact',
        'users',
        'email IS NOT NULL OR phone IS NOT NULL',
        schema='auth'
    )

    # Named unique constraints for phone and user_id
    op.create_unique_constraint(
        'users_phone_key',
        'users',
        ['phone'],
        schema='auth'
    )
    op.create_unique_constraint(
        'users_user_id_key',
        'users',
        ['user_id'],
        schema='auth'
    )

    # Self-referential FK: referred_by → users.user_id
    op.create_foreign_key(
        'fk_referred_by',
        'users',
        'users',
        ['referred_by'],
        ['user_id'],
        source_schema='auth',
        referent_schema='auth'
    )

    # Indexes
    op.create_index('idx_users_email', 'users', ['email'], unique=False, schema='auth')
    op.create_index('idx_users_phone', 'users', ['phone'], unique=False, schema='auth')
    op.create_index('idx_users_status', 'users', ['status'], unique=False, schema='auth')


def downgrade() -> None:
    op.drop_index('idx_users_status', table_name='users', schema='auth')
    op.drop_index('idx_users_phone', table_name='users', schema='auth')
    op.drop_index('idx_users_email', table_name='users', schema='auth')
    op.drop_constraint('fk_referred_by', 'users', schema='auth', type_='foreignkey')
    op.drop_constraint('users_user_id_key', 'users', schema='auth', type_='unique')
    op.drop_constraint('users_phone_key', 'users', schema='auth', type_='unique')
    op.drop_constraint('chk_users_contact', 'users', schema='auth', type_='check')
