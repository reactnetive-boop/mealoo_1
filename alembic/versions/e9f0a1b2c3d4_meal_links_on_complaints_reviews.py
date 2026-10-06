"""complaints and reviews can point at one subscription meal

Revision ID: e9f0a1b2c3d4
Revises: d0e1f2a3b4c5
Create Date: 2026-10-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (("complaints", "complaints_subscription_order_id_fkey"), ("reviews", "reviews_subscription_order_id_fkey"))


def upgrade() -> None:
    for table, fk in TABLES:
        op.add_column(
            table,
            sa.Column(
                "subscription_order_reference_id", postgresql.UUID(as_uuid=True),
                sa.ForeignKey("subscription.orders.order_id", name=fk), nullable=True,
            ),
            schema="provider",
        )
    op.create_index(
        "ix_provider_complaints_subscription_order_reference_id", "complaints",
        ["subscription_order_reference_id"], schema="provider",
    )


def downgrade() -> None:
    op.drop_index("ix_provider_complaints_subscription_order_reference_id", table_name="complaints", schema="provider")
    for table, _ in TABLES:
        op.drop_column(table, "subscription_order_reference_id", schema="provider")
