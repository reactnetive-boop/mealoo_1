"""add daily_meal_quota and fssai_licence to providers

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-09-25 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 14-digit FSSAI food business licence number
    op.add_column(
        'providers',
        sa.Column(
            'fssai_licence',
            sa.String(length=14),
            nullable=True,
        ),
        schema='provider'
    )

    # NULL means no provider-level limit; a positive integer caps the total
    # meals served per individual meal-slot per day across all packages
    op.add_column(
        'providers',
        sa.Column(
            'daily_meal_quota',
            sa.SmallInteger(),
            nullable=True,
        ),
        schema='provider'
    )
    op.create_check_constraint(
        'chk_providers_daily_meal_quota_positive',
        'providers',
        'daily_meal_quota IS NULL OR daily_meal_quota > 0',
        schema='provider'
    )


def downgrade() -> None:
    op.drop_constraint(
        'chk_providers_daily_meal_quota_positive',
        'providers',
        schema='provider'
    )
    op.drop_column(
        'providers',
        'daily_meal_quota',
        schema='provider'
    )
    op.drop_column(
        'providers',
        'fssai_licence',
        schema='provider'
    )
