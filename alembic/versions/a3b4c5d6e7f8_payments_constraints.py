"""payments constraints

Revision ID: a3b4c5d6e7f8
Revises: f7a2b3c4d5e6
Create Date: 2026-06-16 18:50:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f7a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK constraints
    op.create_check_constraint(
        'chk_payment_amount',
        'payments',
        'amount > 0',
        schema='subscription'
    )
    op.create_check_constraint(
        'chk_payment_ref',
        'payments',
        'subscription_id IS NOT NULL OR extra_order_id IS NOT NULL',
        schema='subscription'
    )

    # UNIQUE on gateway_txn_id
    op.create_unique_constraint(
        'payments_gateway_txn_id_key',
        'payments',
        ['gateway_txn_id'],
        schema='subscription'
    )

    # FK constraints
    op.create_foreign_key(
        'payments_user_id_fkey',
        'payments', 'users',
        ['user_id'], ['user_id'],
        source_schema='subscription',
        referent_schema='auth'
    )
    op.create_foreign_key(
        'payments_subscription_id_fkey',
        'payments', 'subscriptions',
        ['subscription_id'], ['id'],
        source_schema='subscription',
        referent_schema='subscription'
    )
    op.create_foreign_key(
        'payments_extra_order_id_fkey',
        'payments', 'extra_orders',
        ['extra_order_id'], ['id'],
        source_schema='subscription',
        referent_schema='subscription'
    )


def downgrade() -> None:
    op.drop_constraint('payments_extra_order_id_fkey', 'payments', schema='subscription', type_='foreignkey')
    op.drop_constraint('payments_subscription_id_fkey', 'payments', schema='subscription', type_='foreignkey')
    op.drop_constraint('payments_user_id_fkey', 'payments', schema='subscription', type_='foreignkey')
    op.drop_constraint('payments_gateway_txn_id_key', 'payments', schema='subscription', type_='unique')
    op.drop_constraint('chk_payment_ref', 'payments', schema='subscription', type_='check')
    op.drop_constraint('chk_payment_amount', 'payments', schema='subscription', type_='check')
