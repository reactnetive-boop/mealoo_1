"""add provider_unavailability table and is_accepting_orders to providers

Revision ID: 2e1d0c9b8a7f
Revises: 3f2e1d0c9b8a
Create Date: 2026-06-18 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '2e1d0c9b8a7f'
down_revision: Union[str, None] = '3f2e1d0c9b8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_accepting_orders to providers
    op.add_column(
        'providers',
        sa.Column('is_accepting_orders', sa.Boolean(), nullable=False, server_default='true'),
        schema='provider'
    )

    # Create provider_unavailability table
    op.create_table(
        'provider_unavailability',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('provider_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('unavailable_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ['provider_id'], ['provider.providers.provider_id'],
            name='provider_unavail_provider_id_fkey'
        ),
        sa.UniqueConstraint('provider_id', 'unavailable_date', name='uq_provider_unavailability_date'),
        schema='provider'
    )
    op.create_index(
        'idx_provider_unavail_date',
        'provider_unavailability',
        ['provider_id', 'unavailable_date'],
        schema='provider'
    )


def downgrade() -> None:
    op.drop_index('idx_provider_unavail_date', 'provider_unavailability', schema='provider')
    op.drop_table('provider_unavailability', schema='provider')
    op.drop_column('providers', 'is_accepting_orders', schema='provider')
