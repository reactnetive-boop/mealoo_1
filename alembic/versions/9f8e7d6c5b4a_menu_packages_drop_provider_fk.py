"""menu_packages drop provider_id FK to allow admin_users as providers

Revision ID: 9f8e7d6c5b4a
Revises: f8a3b4c5d6e7
Create Date: 2026-06-17 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = '9f8e7d6c5b4a'
down_revision: Union[str, Sequence[str], None] = 'f8a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop FK so admin_users can also be valid provider_id values.
    # Validation is handled at the application layer (check providers OR admin_users).
    op.drop_constraint(
        'menu_packages_provider_id_fkey',
        'menu_packages',
        schema='master',
        type_='foreignkey'
    )


def downgrade() -> None:
    op.create_foreign_key(
        'menu_packages_provider_id_fkey',
        'menu_packages', 'providers',
        ['provider_id'], ['provider_id'],
        source_schema='master',
        referent_schema='provider'
    )
