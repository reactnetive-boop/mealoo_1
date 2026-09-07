"""add delivery boy tables and order columns

Revision ID: 5b4a3f2e1d0c
Revises: 6c5b4a3f2e1d
Create Date: 2026-06-18 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op


revision: str = '5b4a3f2e1d0c'
down_revision: Union[str, None] = '6c5b4a3f2e1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create delivery schema
    op.execute("CREATE SCHEMA IF NOT EXISTS delivery")

    # ── delivery_boys ─────────────────────────────────────
    op.create_table(
        'delivery_boys',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('delivery_boy_id', UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('mobile_number', sa.String(15), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String, nullable=False),
        sa.Column('full_name', sa.String(128), nullable=True),
        sa.Column('is_mobile_verified', sa.Boolean, server_default='false'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('vehicle_type', sa.String(30), nullable=True),
        sa.Column('vehicle_number', sa.String(20), nullable=True),
        sa.Column('profile_image', sa.Text, nullable=True),
        sa.Column('assigned_provider_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['assigned_provider_id'],
            ['provider.providers.provider_id'],
            name='delivery_boys_assigned_provider_id_fkey'
        ),
        sa.UniqueConstraint('mobile_number', name='delivery_boys_mobile_number_key'),
        sa.UniqueConstraint('delivery_boy_id', name='delivery_boys_delivery_boy_id_key'),
        schema='delivery'
    )
    op.create_index('idx_delivery_boys_mobile', 'delivery_boys', ['mobile_number'], schema='delivery')
    op.create_index('idx_delivery_boys_provider', 'delivery_boys', ['assigned_provider_id'], schema='delivery')

    # ── delivery_boy_otp_logs ─────────────────────────────
    op.create_table(
        'delivery_boy_otp_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('mobile_number', sa.String(15), nullable=False),
        sa.Column('otp', sa.String(6), nullable=False),
        sa.Column('hashed_password', sa.String, nullable=False),
        sa.Column('is_verified', sa.Boolean, server_default='false'),
        sa.Column('attempts', sa.Integer, server_default='0'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema='delivery'
    )
    op.create_index('idx_delivery_otp_mobile', 'delivery_boy_otp_logs', ['mobile_number'], schema='delivery')

    # ── Add delivery_boy_id to subscription.orders ────────
    op.add_column(
        'orders',
        sa.Column('delivery_boy_id', UUID(as_uuid=True), nullable=True),
        schema='subscription'
    )
    op.create_foreign_key(
        'orders_delivery_boy_id_fkey',
        'orders', 'delivery_boys',
        ['delivery_boy_id'], ['delivery_boy_id'],
        source_schema='subscription',
        referent_schema='delivery'
    )
    op.create_index('idx_orders_delivery_boy', 'orders', ['delivery_boy_id'], schema='subscription')

    # ── Add delivery_boy_id to subscription.extra_orders ──
    op.add_column(
        'extra_orders',
        sa.Column('delivery_boy_id', UUID(as_uuid=True), nullable=True),
        schema='subscription'
    )
    op.create_foreign_key(
        'extra_orders_delivery_boy_id_fkey',
        'extra_orders', 'delivery_boys',
        ['delivery_boy_id'], ['delivery_boy_id'],
        source_schema='subscription',
        referent_schema='delivery'
    )
    op.create_index('idx_extra_orders_delivery_boy', 'extra_orders', ['delivery_boy_id'], schema='subscription')


def downgrade() -> None:
    op.drop_index('idx_extra_orders_delivery_boy', 'extra_orders', schema='subscription')
    op.drop_constraint('extra_orders_delivery_boy_id_fkey', 'extra_orders', schema='subscription', type_='foreignkey')
    op.drop_column('extra_orders', 'delivery_boy_id', schema='subscription')

    op.drop_index('idx_orders_delivery_boy', 'orders', schema='subscription')
    op.drop_constraint('orders_delivery_boy_id_fkey', 'orders', schema='subscription', type_='foreignkey')
    op.drop_column('orders', 'delivery_boy_id', schema='subscription')

    op.drop_table('delivery_boy_otp_logs', schema='delivery')
    op.drop_table('delivery_boys', schema='delivery')
    op.execute("DROP SCHEMA IF EXISTS delivery CASCADE")
