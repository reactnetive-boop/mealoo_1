"""menu_packages indexes

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-06-16 17:50:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f6a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'e5f6a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'idx_menu_packages_provider',
        'menu_packages',
        ['provider_id'],
        unique=False,
        schema='master'
    )
    op.create_index(
        'idx_menu_packages_category',
        'menu_packages',
        ['category_id'],
        unique=False,
        schema='master'
    )
    op.create_index(
        'idx_menu_packages_active',
        'menu_packages',
        ['is_active'],
        unique=False,
        schema='master'
    )
    op.create_index(
        'idx_menu_packages_available',
        'menu_packages',
        ['is_available'],
        unique=False,
        schema='master'
    )


def downgrade() -> None:
    op.drop_index('idx_menu_packages_available', table_name='menu_packages', schema='master')
    op.drop_index('idx_menu_packages_active', table_name='menu_packages', schema='master')
    op.drop_index('idx_menu_packages_category', table_name='menu_packages', schema='master')
    op.drop_index('idx_menu_packages_provider', table_name='menu_packages', schema='master')
