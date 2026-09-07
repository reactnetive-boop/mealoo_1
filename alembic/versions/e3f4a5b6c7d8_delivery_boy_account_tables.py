"""delivery boy account tables (documents, payout, wallet, notifications, is_online)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-13 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from alembic import op


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Duty status on the delivery boy itself ────────────
    op.add_column(
        'delivery_boys',
        sa.Column('is_online', sa.Boolean, nullable=False, server_default='true'),
        schema='delivery'
    )

    # ── Documents ─────────────────────────────────────────
    op.create_table(
        'delivery_boy_documents',
        sa.Column('delivery_boy_document_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('delivery_boy_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('document_type', sa.String(50), nullable=False),
        sa.Column('file_url', sa.Text, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['delivery_boy_reference_id'],
            ['delivery.delivery_boys.delivery_boy_id'],
            name='delivery_boy_documents_delivery_boy_id_fkey'
        ),
        sa.UniqueConstraint(
            'delivery_boy_reference_id', 'document_type',
            name='uq_delivery_boy_document_type'
        ),
        schema='delivery'
    )
    op.create_index(
        'idx_delivery_boy_documents_boy',
        'delivery_boy_documents', ['delivery_boy_reference_id'],
        schema='delivery'
    )

    # ── Payout details ────────────────────────────────────
    op.create_table(
        'delivery_boy_payout_details',
        sa.Column('delivery_boy_payout_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('delivery_boy_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('account_holder_name', sa.String(128), nullable=True),
        sa.Column('account_number', sa.String(30), nullable=True),
        sa.Column('ifsc_code', sa.String(20), nullable=True),
        sa.Column('bank_name', sa.String(128), nullable=True),
        sa.Column('upi_id', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['delivery_boy_reference_id'],
            ['delivery.delivery_boys.delivery_boy_id'],
            name='delivery_boy_payout_delivery_boy_id_fkey'
        ),
        sa.UniqueConstraint(
            'delivery_boy_reference_id',
            name='uq_delivery_boy_payout_boy'
        ),
        schema='delivery'
    )

    # ── Wallet ────────────────────────────────────────────
    op.create_table(
        'delivery_boy_wallets',
        sa.Column('delivery_boy_wallet_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('delivery_boy_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('balance', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('total_earned', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('total_withdrawn', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['delivery_boy_reference_id'],
            ['delivery.delivery_boys.delivery_boy_id'],
            name='delivery_boy_wallets_delivery_boy_id_fkey'
        ),
        sa.UniqueConstraint(
            'delivery_boy_reference_id',
            name='delivery_boy_wallets_boy_id_key'
        ),
        sa.CheckConstraint('balance >= 0', name='chk_delivery_boy_wallet_balance'),
        schema='delivery'
    )

    op.create_table(
        'delivery_boy_wallet_transactions',
        sa.Column('delivery_boy_wallet_transaction_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('wallet_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('delivery_boy_reference_id', UUID(as_uuid=True), nullable=False),
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
            ['wallet_reference_id'],
            ['delivery.delivery_boy_wallets.delivery_boy_wallet_id'],
            name='delivery_boy_wtxn_wallet_id_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['delivery_boy_reference_id'],
            ['delivery.delivery_boys.delivery_boy_id'],
            name='delivery_boy_wtxn_delivery_boy_id_fkey'
        ),
        sa.CheckConstraint('amount > 0', name='chk_delivery_boy_wtxn_amount'),
        schema='delivery'
    )
    op.create_index('idx_delivery_boy_wtxn_boy', 'delivery_boy_wallet_transactions', ['delivery_boy_reference_id'], schema='delivery')
    op.create_index('idx_delivery_boy_wtxn_wallet', 'delivery_boy_wallet_transactions', ['wallet_reference_id'], schema='delivery')
    op.create_index('idx_delivery_boy_wtxn_type', 'delivery_boy_wallet_transactions', ['type'], schema='delivery')

    # ── Notifications ─────────────────────────────────────
    op.create_table(
        'delivery_boy_notifications',
        sa.Column('delivery_boy_notification_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('delivery_boy_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(150), nullable=False),
        sa.Column('body', sa.Text, nullable=False),
        sa.Column('data', JSONB, nullable=True),
        sa.Column('is_read', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['delivery_boy_reference_id'],
            ['delivery.delivery_boys.delivery_boy_id'],
            name='delivery_boy_notifications_delivery_boy_id_fkey'
        ),
        schema='delivery'
    )
    op.create_index('idx_delivery_boy_notifications_boy', 'delivery_boy_notifications', ['delivery_boy_reference_id'], schema='delivery')
    op.create_index('idx_delivery_boy_notifications_unread', 'delivery_boy_notifications', ['delivery_boy_reference_id', 'is_read'], schema='delivery')


def downgrade() -> None:
    op.drop_table('delivery_boy_notifications', schema='delivery')
    op.drop_table('delivery_boy_wallet_transactions', schema='delivery')
    op.drop_table('delivery_boy_wallets', schema='delivery')
    op.drop_table('delivery_boy_payout_details', schema='delivery')
    op.drop_table('delivery_boy_documents', schema='delivery')
    op.drop_column('delivery_boys', 'is_online', schema='delivery')
