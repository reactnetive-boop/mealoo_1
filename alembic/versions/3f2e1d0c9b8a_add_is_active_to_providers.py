"""add is_active to providers

Revision ID: 3f2e1d0c9b8a
Revises: 4a3f2e1d0c9b
Create Date: 2026-06-18 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '3f2e1d0c9b8a'
down_revision: Union[str, None] = '4a3f2e1d0c9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'providers',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        schema='provider'
    )
    op.create_index('idx_providers_is_active', 'providers', ['is_active'], schema='provider')


def downgrade() -> None:
    op.drop_index('idx_providers_is_active', 'providers', schema='provider')
    op.drop_column('providers', 'is_active', schema='provider')
