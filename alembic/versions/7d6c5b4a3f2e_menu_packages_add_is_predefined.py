"""menu_packages add is_predefined column

Revision ID: 7d6c5b4a3f2e
Revises: 8e7d6c5b4a3f
Create Date: 2026-06-17 12:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '7d6c5b4a3f2e'
down_revision: Union[str, Sequence[str], None] = '8e7d6c5b4a3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'menu_packages',
        sa.Column(
            'is_predefined',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False
        ),
        schema='master'
    )


def downgrade() -> None:
    op.drop_column('menu_packages', 'is_predefined', schema='master')
