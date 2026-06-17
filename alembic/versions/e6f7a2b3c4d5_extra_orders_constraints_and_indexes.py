"""extra_orders constraints and indexes

Revision ID: e6f7a2b3c4d5
Revises: d5e6f7a2b3c4
Create Date: 2026-06-16 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e6f7a2b3c4d5'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK: quantity must be 1-5
    op.create_check_constraint(
        'chk_extra_qty',
        'extra_orders',
        'quantity >= 1 AND quantity <= 5',
        schema='subscription'
    )

    # FK constraints
    op.create_foreign_key(
        'extra_orders_user_id_fkey',
        'extra_orders', 'users',
        ['user_id'], ['user_id'],
        source_schema='subscription',
        referent_schema='auth'
    )
    op.create_foreign_key(
        'extra_orders_vendor_id_fkey',
        'extra_orders', 'providers',
        ['vendor_id'], ['provider_id'],
        source_schema='subscription',
        referent_schema='provider'
    )
    op.create_foreign_key(
        'extra_orders_address_id_fkey',
        'extra_orders', 'user_addresses',
        ['address_id'], ['id'],
        source_schema='subscription',
        referent_schema='auth'
    )
    op.create_foreign_key(
        'extra_orders_package_id_fkey',
        'extra_orders', 'menu_packages',
        ['package_id'], ['package_id'],
        source_schema='subscription',
        referent_schema='master'
    )

    # Indexes
    op.create_index('idx_extra_orders_user', 'extra_orders', ['user_id'], unique=False, schema='subscription')
    op.create_index('idx_extra_orders_vendor', 'extra_orders', ['vendor_id'], unique=False, schema='subscription')


def downgrade() -> None:
    op.drop_index('idx_extra_orders_vendor', table_name='extra_orders', schema='subscription')
    op.drop_index('idx_extra_orders_user', table_name='extra_orders', schema='subscription')
    op.drop_constraint('extra_orders_package_id_fkey', 'extra_orders', schema='subscription', type_='foreignkey')
    op.drop_constraint('extra_orders_address_id_fkey', 'extra_orders', schema='subscription', type_='foreignkey')
    op.drop_constraint('extra_orders_vendor_id_fkey', 'extra_orders', schema='subscription', type_='foreignkey')
    op.drop_constraint('extra_orders_user_id_fkey', 'extra_orders', schema='subscription', type_='foreignkey')
    op.drop_constraint('chk_extra_qty', 'extra_orders', schema='subscription', type_='check')
