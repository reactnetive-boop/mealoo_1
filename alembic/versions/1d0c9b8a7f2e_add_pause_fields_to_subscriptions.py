"""add pause fields to subscriptions

Revision ID: 1d0c9b8a7f2e
Revises: 2e1d0c9b8a7f
Create Date: 2026-06-19 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '1d0c9b8a7f2e'
down_revision: Union[str, None] = '2e1d0c9b8a7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Date the current pause started (NULL when not paused)
    op.add_column(
        'subscriptions',
        sa.Column('pause_start_date', sa.Date(), nullable=True),
        schema='subscription'
    )
    # Cumulative calendar days the subscription has been paused across all cycles
    op.add_column(
        'subscriptions',
        sa.Column(
            'total_days_paused',
            sa.Integer(),
            nullable=False,
            server_default='0'
        ),
        schema='subscription'
    )


def downgrade() -> None:
    op.drop_column('subscriptions', 'total_days_paused', schema='subscription')
    op.drop_column('subscriptions', 'pause_start_date', schema='subscription')
