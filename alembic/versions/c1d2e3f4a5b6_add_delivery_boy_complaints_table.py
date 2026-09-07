"""add delivery boy complaints table

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-07-06 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from alembic import op


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'delivery_boy_complaints',
        sa.Column('delivery_boy_complaint_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('delivery_boy_reference_id', UUID(as_uuid=True), nullable=False),
        sa.Column('against', sa.String(30), nullable=False),
        sa.Column('provider_reference_id', UUID(as_uuid=True), nullable=True),
        sa.Column('order_id', UUID(as_uuid=True), nullable=True),
        sa.Column('order_type', sa.String(20), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('evidence_urls', ARRAY(sa.Text), nullable=True),
        sa.Column('admin_notes', sa.Text, nullable=True),
        sa.Column('resolved_by', UUID(as_uuid=True), nullable=True),
        sa.Column('resolution', sa.Text, nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['delivery_boy_reference_id'],
            ['delivery.delivery_boys.delivery_boy_id'],
            name='delivery_boy_complaints_delivery_boy_id_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['provider_reference_id'],
            ['provider.providers.provider_id'],
            name='delivery_boy_complaints_provider_id_fkey'
        ),
        schema='delivery'
    )
    op.create_index('idx_delivery_boy_complaints_delivery_boy', 'delivery_boy_complaints', ['delivery_boy_reference_id'], schema='delivery')
    op.create_index('idx_delivery_boy_complaints_against', 'delivery_boy_complaints', ['against'], schema='delivery')
    op.create_index('idx_delivery_boy_complaints_status', 'delivery_boy_complaints', ['status'], schema='delivery')
    op.create_index('idx_delivery_boy_complaints_provider', 'delivery_boy_complaints', ['provider_reference_id'], schema='delivery')


def downgrade() -> None:
    op.drop_table('delivery_boy_complaints', schema='delivery')
