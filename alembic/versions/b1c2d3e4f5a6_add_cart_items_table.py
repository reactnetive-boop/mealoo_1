"""add cart_items table

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-06-23 01:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a0b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cart_items',
        sa.Column('cart_item_id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_reference_id', UUID(as_uuid=True), sa.ForeignKey('auth.users.user_id', name='cart_items_user_id_fkey'), nullable=False),
        sa.Column('vendor_reference_id', UUID(as_uuid=True), sa.ForeignKey('provider.providers.provider_id', name='cart_items_vendor_id_fkey'), nullable=False),
        sa.Column('package_reference_id', UUID(as_uuid=True), sa.ForeignKey('master.menu_packages.package_id', name='cart_items_package_id_fkey'), nullable=False),
        sa.Column('quantity', sa.SmallInteger(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.UniqueConstraint('user_reference_id', 'package_reference_id', name='uq_cart_user_package'),
        sa.CheckConstraint('quantity >= 1 AND quantity <= 10', name='chk_cart_qty'),
        schema='subscription',
    )
    op.create_index(
        'idx_cart_items_user',
        'cart_items',
        ['user_reference_id'],
        schema='subscription',
    )
    op.create_index(
        'idx_cart_items_cart_item_id',
        'cart_items',
        ['cart_item_id'],
        schema='subscription',
    )


def downgrade() -> None:
    op.drop_index('idx_cart_items_cart_item_id', table_name='cart_items', schema='subscription')
    op.drop_index('idx_cart_items_user', table_name='cart_items', schema='subscription')
    op.drop_table('cart_items', schema='subscription')
