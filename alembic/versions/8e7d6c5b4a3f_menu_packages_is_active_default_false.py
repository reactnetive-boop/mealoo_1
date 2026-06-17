"""menu_packages is_active default changed to false

Revision ID: 8e7d6c5b4a3f
Revises: 9f8e7d6c5b4a
Create Date: 2026-06-17 12:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '8e7d6c5b4a3f'
down_revision: Union[str, Sequence[str], None] = '9f8e7d6c5b4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'menu_packages', 'is_active',
        server_default=sa.text('false'),
        schema='master'
    )


def downgrade() -> None:
    op.alter_column(
        'menu_packages', 'is_active',
        server_default=sa.text('true'),
        schema='master'
    )
