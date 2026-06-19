"""add daily_capacity to provider_selected_packages

Revision ID: 0c9b8a7f2e1d
Revises: 1d0c9b8a7f2e
Create Date: 2026-06-19 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '0c9b8a7f2e1d'
down_revision: Union[str, None] = '1d0c9b8a7f2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL means no limit; a positive integer caps units per meal-slot per day
    op.add_column(
        'provider_selected_packages',
        sa.Column(
            'daily_capacity',
            sa.SmallInteger(),
            nullable=True,
        ),
        schema='provider'
    )
    op.create_check_constraint(
        'chk_psp_capacity_positive',
        'provider_selected_packages',
        'daily_capacity IS NULL OR daily_capacity > 0',
        schema='provider'
    )


def downgrade() -> None:
    op.drop_constraint(
        'chk_psp_capacity_positive',
        'provider_selected_packages',
        schema='provider'
    )
    op.drop_column(
        'provider_selected_packages',
        'daily_capacity',
        schema='provider'
    )
