"""providers unique constraint

Revision ID: c4d5e6f7a2b3
Revises: b3c4d5e6f7a2
Create Date: 2026-06-16 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c4d5e6f7a2b3'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_provider_provider_id',
        'providers',
        ['provider_id'],
        schema='provider'
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_provider_provider_id',
        'providers',
        schema='provider',
        type_='unique'
    )
