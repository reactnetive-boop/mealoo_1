"""delivery partner leave days

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-10-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "delivery_boy_leaves",
        sa.Column("delivery_boy_leave_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "delivery_boy_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery.delivery_boys.delivery_boy_id", name="delivery_boy_leaves_delivery_boy_id_fkey"),
            nullable=False,
        ),
        sa.Column("leave_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(255)),
        sa.Column("created_by_type", sa.String(20), nullable=False, server_default="delivery_boy"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("delivery_boy_reference_id", "leave_date", name="uq_delivery_boy_leave_day"),
        schema="delivery",
    )
    op.create_index("ix_delivery_delivery_boy_leaves_delivery_boy_reference_id", "delivery_boy_leaves",
                    ["delivery_boy_reference_id"], schema="delivery")
    op.create_index("ix_delivery_delivery_boy_leaves_leave_date", "delivery_boy_leaves", ["leave_date"], schema="delivery")


def downgrade() -> None:
    op.drop_index("ix_delivery_delivery_boy_leaves_leave_date", table_name="delivery_boy_leaves", schema="delivery")
    op.drop_index("ix_delivery_delivery_boy_leaves_delivery_boy_reference_id", table_name="delivery_boy_leaves",
                  schema="delivery")
    op.drop_table("delivery_boy_leaves", schema="delivery")
