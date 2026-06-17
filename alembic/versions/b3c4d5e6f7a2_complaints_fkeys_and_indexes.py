"""complaints fkeys and indexes

Revision ID: b3c4d5e6f7a2
Revises: a2b3c4d5e6f7
Create Date: 2026-06-16 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b3c4d5e6f7a2'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FK → auth.users.user_id
    op.create_foreign_key(
        'complaints_user_id_fkey',
        'complaints', 'users',
        ['user_id'], ['user_id'],
        source_schema='provider',
        referent_schema='auth'
    )

    # FK → provider.providers.provider_id
    op.create_foreign_key(
        'complaints_vendor_id_fkey',
        'complaints', 'providers',
        ['vendor_id'], ['provider_id'],
        source_schema='provider',
        referent_schema='provider'
    )

    # FK → subscription.subscriptions.id
    op.create_foreign_key(
        'complaints_subscription_id_fkey',
        'complaints', 'subscriptions',
        ['subscription_id'], ['id'],
        source_schema='provider',
        referent_schema='subscription'
    )

    # FK → subscription.extra_orders.id
    op.create_foreign_key(
        'complaints_order_id_fkey',
        'complaints', 'extra_orders',
        ['order_id'], ['id'],
        source_schema='provider',
        referent_schema='subscription'
    )

    # Indexes
    op.create_index('idx_complaints_user', 'complaints', ['user_id'], unique=False, schema='provider')
    op.create_index('idx_complaints_vendor', 'complaints', ['vendor_id'], unique=False, schema='provider')
    op.create_index('idx_complaints_status', 'complaints', ['status'], unique=False, schema='provider')


def downgrade() -> None:
    op.drop_index('idx_complaints_status', table_name='complaints', schema='provider')
    op.drop_index('idx_complaints_vendor', table_name='complaints', schema='provider')
    op.drop_index('idx_complaints_user', table_name='complaints', schema='provider')
    op.drop_constraint('complaints_order_id_fkey', 'complaints', schema='provider', type_='foreignkey')
    op.drop_constraint('complaints_subscription_id_fkey', 'complaints', schema='provider', type_='foreignkey')
    op.drop_constraint('complaints_vendor_id_fkey', 'complaints', schema='provider', type_='foreignkey')
    op.drop_constraint('complaints_user_id_fkey', 'complaints', schema='provider', type_='foreignkey')
