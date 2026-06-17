"""add orders table

Revision ID: f7a2b3c4d5e6
Revises: e6f7a2b3c4d5
Create Date: 2026-06-16 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f7a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e6f7a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'orders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('subscription_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('vendor_id', sa.UUID(), nullable=False),
        sa.Column('delivery_address_id', sa.UUID(), nullable=False),
        sa.Column('order_date', sa.Date(), nullable=False),
        sa.Column('meal_slot', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('is_free_skip', sa.Boolean(), nullable=False),
        sa.Column('skip_requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('skip_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivery_notes', sa.Text(), nullable=True),
        sa.Column('otp_for_delivery', sa.String(length=6), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='orders_pkey'),
        sa.UniqueConstraint(
            'subscription_id', 'order_date', 'meal_slot',
            name='orders_subscription_id_order_date_meal_slot_key'
        ),
        sa.ForeignKeyConstraint(
            ['subscription_id'], ['subscription.subscriptions.id'],
            name='orders_subscription_id_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['auth.users.user_id'],
            name='orders_user_id_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['vendor_id'], ['provider.providers.provider_id'],
            name='orders_vendor_id_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['delivery_address_id'], ['auth.user_addresses.id'],
            name='orders_delivery_address_id_fkey'
        ),
        schema='subscription'
    )

    op.create_index('idx_orders_sub', 'orders', ['subscription_id'], unique=False, schema='subscription')
    op.create_index('idx_orders_user', 'orders', ['user_id'], unique=False, schema='subscription')
    op.create_index('idx_orders_vendor', 'orders', ['vendor_id'], unique=False, schema='subscription')
    op.create_index('idx_orders_date_status', 'orders', ['order_date', 'status'], unique=False, schema='subscription')


def downgrade() -> None:
    op.drop_index('idx_orders_date_status', table_name='orders', schema='subscription')
    op.drop_index('idx_orders_vendor', table_name='orders', schema='subscription')
    op.drop_index('idx_orders_user', table_name='orders', schema='subscription')
    op.drop_index('idx_orders_sub', table_name='orders', schema='subscription')
    op.drop_table('orders', schema='subscription')
