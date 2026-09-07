"""add purpose column to payments and relax chk_payment_ref

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-06 12:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'payments',
        sa.Column('purpose', sa.String(20), nullable=False, server_default='wallet_topup'),
        schema='subscription'
    )
    op.drop_constraint('chk_payment_ref', 'payments', schema='subscription', type_='check')
    op.create_check_constraint(
        'chk_payment_ref',
        'payments',
        "subscription_reference_id IS NOT NULL OR extra_order_reference_id IS NOT NULL OR purpose = 'wallet_topup'",
        schema='subscription'
    )


def downgrade() -> None:
    op.drop_constraint('chk_payment_ref', 'payments', schema='subscription', type_='check')
    op.create_check_constraint(
        'chk_payment_ref',
        'payments',
        "subscription_reference_id IS NOT NULL OR extra_order_reference_id IS NOT NULL",
        schema='subscription'
    )
    op.drop_column('payments', 'purpose', schema='subscription')
