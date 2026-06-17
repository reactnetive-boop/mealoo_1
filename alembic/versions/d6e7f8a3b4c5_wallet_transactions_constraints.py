"""wallet_transactions constraints and indexes

Revision ID: d6e7f8a3b4c5
Revises: c5d6e7f8a3b4
Create Date: 2026-06-16 21:25:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd6e7f8a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK: amount must be positive
    op.create_check_constraint(
        'chk_wtxn_amount',
        'wallet_transactions',
        'amount > 0',
        schema='subscription'
    )

    # FK constraints
    op.create_foreign_key(
        'wallet_transactions_user_id_fkey',
        'wallet_transactions', 'users',
        ['user_id'], ['user_id'],
        source_schema='subscription',
        referent_schema='auth'
    )
    op.create_foreign_key(
        'wallet_transactions_wallet_id_fkey',
        'wallet_transactions', 'wallets',
        ['wallet_id'], ['id'],
        source_schema='subscription',
        referent_schema='subscription'
    )

    # Indexes
    op.create_index('idx_wallet_txn_user', 'wallet_transactions', ['user_id'], unique=False, schema='subscription')
    op.create_index('idx_wallet_txn_wallet', 'wallet_transactions', ['wallet_id'], unique=False, schema='subscription')


def downgrade() -> None:
    op.drop_index('idx_wallet_txn_wallet', table_name='wallet_transactions', schema='subscription')
    op.drop_index('idx_wallet_txn_user', table_name='wallet_transactions', schema='subscription')
    op.drop_constraint('wallet_transactions_wallet_id_fkey', 'wallet_transactions', schema='subscription', type_='foreignkey')
    op.drop_constraint('wallet_transactions_user_id_fkey', 'wallet_transactions', schema='subscription', type_='foreignkey')
    op.drop_constraint('chk_wtxn_amount', 'wallet_transactions', schema='subscription', type_='check')
