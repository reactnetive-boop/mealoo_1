"""user_addresses constraints and indexes

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-06-16 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a1'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK constraints
    op.create_check_constraint(
        'user_addresses_latitude_check',
        'user_addresses',
        'latitude >= -90 AND latitude <= 90',
        schema='auth'
    )
    op.create_check_constraint(
        'user_addresses_longitude_check',
        'user_addresses',
        'longitude >= -180 AND longitude <= 180',
        schema='auth'
    )

    # FK → auth.users.user_id
    op.create_foreign_key(
        'user_addresses_user_id_fkey',
        'user_addresses',
        'users',
        ['user_id'],
        ['user_id'],
        source_schema='auth',
        referent_schema='auth'
    )

    # Indexes
    op.create_index(
        'idx_user_addresses_user',
        'user_addresses',
        ['user_id'],
        unique=False,
        schema='auth'
    )
    op.create_index(
        'idx_user_addresses_pincode',
        'user_addresses',
        ['pin_code'],
        unique=False,
        schema='auth'
    )


def downgrade() -> None:
    op.drop_index('idx_user_addresses_pincode', table_name='user_addresses', schema='auth')
    op.drop_index('idx_user_addresses_user', table_name='user_addresses', schema='auth')
    op.drop_constraint('user_addresses_user_id_fkey', 'user_addresses', schema='auth', type_='foreignkey')
    op.drop_constraint('user_addresses_longitude_check', 'user_addresses', schema='auth', type_='check')
    op.drop_constraint('user_addresses_latitude_check', 'user_addresses', schema='auth', type_='check')
