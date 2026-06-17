"""subscription_packages constraints

Revision ID: b4c5d6e7f8a3
Revises: a3b4c5d6e7f8
Create Date: 2026-06-16 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b4c5d6e7f8a3'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK: quantity must be > 0
    op.create_check_constraint(
        'chk_sub_pkg_qty',
        'subscription_packages',
        'quantity > 0',
        schema='subscription'
    )

    # FK → master.menu_packages.package_id
    op.create_foreign_key(
        'subscription_packages_package_id_fkey',
        'subscription_packages', 'menu_packages',
        ['package_id'], ['package_id'],
        source_schema='subscription',
        referent_schema='master'
    )

    # Index on subscription_id
    op.create_index(
        'idx_sub_packages_subscription',
        'subscription_packages',
        ['subscription_id'],
        unique=False,
        schema='subscription'
    )


def downgrade() -> None:
    op.drop_index('idx_sub_packages_subscription', table_name='subscription_packages', schema='subscription')
    op.drop_constraint('subscription_packages_package_id_fkey', 'subscription_packages', schema='subscription', type_='foreignkey')
    op.drop_constraint('chk_sub_pkg_qty', 'subscription_packages', schema='subscription', type_='check')
