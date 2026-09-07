"""wallets constraints

Revision ID: e7f8a3b4c5d6
Revises: d6e7f8a3b4c5
Create Date: 2026-06-16 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e7f8a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd6e7f8a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK: balance must be non-negative
    op.create_check_constraint(
        'chk_wallet_balance',
        'wallets',
        'balance >= 0',
        schema='subscription'
    )

    # UNIQUE: one wallet per user
    op.create_unique_constraint(
        'wallets_user_id_key',
        'wallets',
        ['user_id'],
        schema='subscription'
    )

    # FK: user_id -> auth.users
    op.create_foreign_key(
        'wallets_user_id_fkey',
        'wallets', 'users',
        ['user_id'], ['user_id'],
        source_schema='subscription',
        referent_schema='auth'
    )


def downgrade() -> None:
    op.drop_constraint('wallets_user_id_fkey', 'wallets', schema='subscription', type_='foreignkey')
    op.drop_constraint('wallets_user_id_key', 'wallets', schema='subscription', type_='unique')
    op.drop_constraint('chk_wallet_balance', 'wallets', schema='subscription', type_='check')
