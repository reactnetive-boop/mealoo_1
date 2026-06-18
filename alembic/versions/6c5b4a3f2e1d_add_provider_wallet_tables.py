"""add provider wallet tables

Revision ID: 6c5b4a3f2e1d
Revises: 7d6c5b4a3f2e
Create Date: 2026-06-18 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op


revision: str = '6c5b4a3f2e1d'
down_revision: Union[str, None] = '7d6c5b4a3f2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'provider_wallets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('provider_id', UUID(as_uuid=True), nullable=False),
        sa.Column('balance', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('total_earned', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('total_withdrawn', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['provider_id'],
            ['provider.providers.provider_id'],
            name='provider_wallets_provider_id_fkey'
        ),
        sa.CheckConstraint('balance >= 0', name='chk_provider_wallet_balance'),
        sa.UniqueConstraint('provider_id', name='provider_wallets_provider_id_key'),
        schema='provider'
    )
    op.create_index('idx_provider_wallets_provider', 'provider_wallets', ['provider_id'], schema='provider')

    op.create_table(
        'provider_wallet_transactions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('wallet_id', UUID(as_uuid=True), nullable=False),
        sa.Column('provider_id', UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('reason', sa.String(50), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('balance_before', sa.Numeric(12, 2), nullable=False),
        sa.Column('balance_after', sa.Numeric(12, 2), nullable=False),
        sa.Column('reference_id', UUID(as_uuid=True), nullable=True),
        sa.Column('reference_type', sa.String(50), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['wallet_id'],
            ['provider.provider_wallets.id'],
            name='provider_wallet_txn_wallet_id_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['provider_id'],
            ['provider.providers.provider_id'],
            name='provider_wallet_txn_provider_id_fkey'
        ),
        sa.CheckConstraint('amount > 0', name='chk_provider_wtxn_amount'),
        schema='provider'
    )
    op.create_index('idx_provider_wtxn_provider', 'provider_wallet_transactions', ['provider_id'], schema='provider')
    op.create_index('idx_provider_wtxn_wallet', 'provider_wallet_transactions', ['wallet_id'], schema='provider')
    op.create_index('idx_provider_wtxn_type', 'provider_wallet_transactions', ['type'], schema='provider')


def downgrade() -> None:
    op.drop_table('provider_wallet_transactions', schema='provider')
    op.drop_table('provider_wallets', schema='provider')
