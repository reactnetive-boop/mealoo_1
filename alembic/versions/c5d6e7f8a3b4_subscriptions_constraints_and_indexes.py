"""subscriptions constraints and indexes

Revision ID: c5d6e7f8a3b4
Revises: b4c5d6e7f8a3
Create Date: 2026-06-16 21:20:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c5d6e7f8a3b4'
down_revision: Union[str, Sequence[str], None] = 'b4c5d6e7f8a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK constraints
    op.create_check_constraint(
        'chk_sub_amount',
        'subscriptions',
        'final_amount > 0',
        schema='subscription'
    )
    op.create_check_constraint(
        'chk_sub_dates',
        'subscriptions',
        'end_date > start_date',
        schema='subscription'
    )
    op.create_check_constraint(
        'chk_sub_skips',
        'subscriptions',
        'free_skips_used <= free_skips_total',
        schema='subscription'
    )

    # FK constraints
    op.create_foreign_key(
        'subscriptions_user_id_fkey',
        'subscriptions', 'users',
        ['user_id'], ['user_id'],
        source_schema='subscription',
        referent_schema='auth'
    )
    op.create_foreign_key(
        'subscriptions_vendor_id_fkey',
        'subscriptions', 'providers',
        ['vendor_id'], ['provider_id'],
        source_schema='subscription',
        referent_schema='provider'
    )
    op.create_foreign_key(
        'subscriptions_plan_id_fkey',
        'subscriptions', 'subscription_plans',
        ['plan_id'], ['id'],
        source_schema='subscription',
        referent_schema='master'
    )
    op.create_foreign_key(
        'subscriptions_user_address_id_fkey',
        'subscriptions', 'user_addresses',
        ['user_address_id'], ['id'],
        source_schema='subscription',
        referent_schema='auth'
    )

    # Indexes
    op.create_index('idx_subscriptions_user', 'subscriptions', ['user_id'], unique=False, schema='subscription')
    op.create_index('idx_subscriptions_vendor', 'subscriptions', ['vendor_id'], unique=False, schema='subscription')
    op.create_index('idx_subscriptions_status', 'subscriptions', ['status'], unique=False, schema='subscription')
    op.create_index('idx_subscriptions_dates', 'subscriptions', ['start_date', 'end_date'], unique=False, schema='subscription')


def downgrade() -> None:
    op.drop_index('idx_subscriptions_dates', table_name='subscriptions', schema='subscription')
    op.drop_index('idx_subscriptions_status', table_name='subscriptions', schema='subscription')
    op.drop_index('idx_subscriptions_vendor', table_name='subscriptions', schema='subscription')
    op.drop_index('idx_subscriptions_user', table_name='subscriptions', schema='subscription')
    op.drop_constraint('subscriptions_user_address_id_fkey', 'subscriptions', schema='subscription', type_='foreignkey')
    op.drop_constraint('subscriptions_plan_id_fkey', 'subscriptions', schema='subscription', type_='foreignkey')
    op.drop_constraint('subscriptions_vendor_id_fkey', 'subscriptions', schema='subscription', type_='foreignkey')
    op.drop_constraint('subscriptions_user_id_fkey', 'subscriptions', schema='subscription', type_='foreignkey')
    op.drop_constraint('chk_sub_skips', 'subscriptions', schema='subscription', type_='check')
    op.drop_constraint('chk_sub_dates', 'subscriptions', schema='subscription', type_='check')
    op.drop_constraint('chk_sub_amount', 'subscriptions', schema='subscription', type_='check')
