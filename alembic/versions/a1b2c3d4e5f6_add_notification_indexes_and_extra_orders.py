"""add notification indexes and extra_orders table

Revision ID: a1b2c3d4e5f6
Revises: 1a3eae9e0b28
Create Date: 2026-06-16 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '1a3eae9e0b28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Missing indexes on auth.notifications ---
    op.create_index(
        'idx_notifications_user',
        'notifications',
        ['user_id'],
        unique=False,
        schema='auth'
    )
    op.create_index(
        'idx_notifications_unread',
        'notifications',
        ['user_id', 'is_read'],
        unique=False,
        schema='auth'
    )

    # --- extra_orders table (subscription schema) ---
    op.create_table(
        'extra_orders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('vendor_id', sa.UUID(), nullable=False),
        sa.Column('address_id', sa.UUID(), nullable=False),
        sa.Column('package_id', sa.UUID(), nullable=False),
        sa.Column('quantity', sa.SmallInteger(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('delivery_date', sa.Date(), nullable=False),
        sa.Column('meal_slot', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='subscription'
    )
    op.create_index(
        op.f('ix_subscription_extra_orders_id'),
        'extra_orders',
        ['id'],
        unique=False,
        schema='subscription'
    )
    op.create_index(
        op.f('ix_subscription_extra_orders_user_id'),
        'extra_orders',
        ['user_id'],
        unique=False,
        schema='subscription'
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_subscription_extra_orders_user_id'),
        table_name='extra_orders',
        schema='subscription'
    )
    op.drop_index(
        op.f('ix_subscription_extra_orders_id'),
        table_name='extra_orders',
        schema='subscription'
    )
    op.drop_table('extra_orders', schema='subscription')

    op.drop_index('idx_notifications_unread', table_name='notifications', schema='auth')
    op.drop_index('idx_notifications_user', table_name='notifications', schema='auth')
