"""orders can end as delivery_failed (customer away, wrong address, refused)

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-10-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("orders", "extra_orders"):
        op.add_column(table, sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True), schema="subscription")
        op.add_column(table, sa.Column("failure_reason", sa.String(40), nullable=True), schema="subscription")


def downgrade() -> None:
    for table in ("orders", "extra_orders"):
        op.drop_column(table, "failure_reason", schema="subscription")
        op.drop_column(table, "failed_at", schema="subscription")
