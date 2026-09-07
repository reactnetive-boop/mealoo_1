"""reviews constraints and indexes

Revision ID: d5e6f7a2b3c4
Revises: c4d5e6f7a2b3
Create Date: 2026-06-16 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd5e6f7a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CHECK constraints
    op.create_check_constraint(
        'chk_vendor_rating',
        'reviews',
        'vendor_rating >= 1 AND vendor_rating <= 5',
        schema='provider'
    )
    op.create_check_constraint(
        'chk_pkg_rating2',
        'reviews',
        'package_rating IS NULL OR (package_rating >= 1 AND package_rating <= 5)',
        schema='provider'
    )

    # FK constraints
    op.create_foreign_key(
        'reviews_user_id_fkey',
        'reviews', 'users',
        ['user_id'], ['user_id'],
        source_schema='provider',
        referent_schema='auth'
    )
    op.create_foreign_key(
        'reviews_vendor_id_fkey',
        'reviews', 'providers',
        ['vendor_id'], ['provider_id'],
        source_schema='provider',
        referent_schema='provider'
    )
    op.create_foreign_key(
        'reviews_subscription_id_fkey',
        'reviews', 'subscriptions',
        ['subscription_id'], ['id'],
        source_schema='provider',
        referent_schema='subscription'
    )
    op.create_foreign_key(
        'reviews_order_id_fkey',
        'reviews', 'extra_orders',
        ['order_id'], ['id'],
        source_schema='provider',
        referent_schema='subscription'
    )
    op.create_foreign_key(
        'reviews_package_id_fkey',
        'reviews', 'menu_packages',
        ['package_id'], ['package_id'],
        source_schema='provider',
        referent_schema='master'
    )

    # Indexes
    op.create_index('idx_reviews_vendor', 'reviews', ['vendor_id'], unique=False, schema='provider')
    op.create_index('idx_reviews_pkg', 'reviews', ['package_id'], unique=False, schema='provider')
    op.create_index(
        'idx_reviews_unique_daily',
        'reviews',
        ['user_id', 'vendor_id', 'review_date'],
        unique=True,
        schema='provider'
    )


def downgrade() -> None:
    op.drop_index('idx_reviews_unique_daily', table_name='reviews', schema='provider')
    op.drop_index('idx_reviews_pkg', table_name='reviews', schema='provider')
    op.drop_index('idx_reviews_vendor', table_name='reviews', schema='provider')
    op.drop_constraint('reviews_package_id_fkey', 'reviews', schema='provider', type_='foreignkey')
    op.drop_constraint('reviews_order_id_fkey', 'reviews', schema='provider', type_='foreignkey')
    op.drop_constraint('reviews_subscription_id_fkey', 'reviews', schema='provider', type_='foreignkey')
    op.drop_constraint('reviews_vendor_id_fkey', 'reviews', schema='provider', type_='foreignkey')
    op.drop_constraint('reviews_user_id_fkey', 'reviews', schema='provider', type_='foreignkey')
    op.drop_constraint('chk_pkg_rating2', 'reviews', schema='provider', type_='check')
    op.drop_constraint('chk_vendor_rating', 'reviews', schema='provider', type_='check')
