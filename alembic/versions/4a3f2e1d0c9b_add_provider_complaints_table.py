"""add provider complaints table

Revision ID: 4a3f2e1d0c9b
Revises: 5b4a3f2e1d0c
Create Date: 2026-06-18 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from alembic import op


revision: str = '4a3f2e1d0c9b'
down_revision: Union[str, None] = '5b4a3f2e1d0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'provider_complaints',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('provider_id', UUID(as_uuid=True), nullable=False),
        sa.Column('against', sa.String(30), nullable=False),
        sa.Column('delivery_boy_id', UUID(as_uuid=True), nullable=True),
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
            ['provider_id'],
            ['provider.providers.provider_id'],
            name='provider_complaints_provider_id_fkey'
        ),
        sa.ForeignKeyConstraint(
            ['delivery_boy_id'],
            ['delivery.delivery_boys.delivery_boy_id'],
            name='provider_complaints_delivery_boy_id_fkey'
        ),
        schema='provider'
    )
    op.create_index('idx_provider_complaints_provider', 'provider_complaints', ['provider_id'], schema='provider')
    op.create_index('idx_provider_complaints_against', 'provider_complaints', ['against'], schema='provider')
    op.create_index('idx_provider_complaints_status', 'provider_complaints', ['status'], schema='provider')
    op.create_index('idx_provider_complaints_delivery_boy', 'provider_complaints', ['delivery_boy_id'], schema='provider')


def downgrade() -> None:
    op.drop_table('provider_complaints', schema='provider')
