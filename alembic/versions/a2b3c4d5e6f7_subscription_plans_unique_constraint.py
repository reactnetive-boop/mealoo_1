"""subscription_plans unique constraint

Revision ID: a2b3c4d5e6f7
Revises: f6a1b2c3d4e5
Create Date: 2026-06-16 17:55:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f6a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'subscription_plans_subscription_type_meal_slot_key',
        'subscription_plans',
        ['subscription_type', 'meal_slot'],
        schema='master'
    )


def downgrade() -> None:
    op.drop_constraint(
        'subscription_plans_subscription_type_meal_slot_key',
        'subscription_plans',
        schema='master',
        type_='unique'
    )
