"""customers can withdraw their wallet balance to a bank / UPI

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-10-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_payout_details",
        sa.Column("user_payout_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth.users.user_id", name="user_payout_user_id_fkey"), nullable=False, unique=True,
        ),
        sa.Column("account_holder_name", sa.String(128)),
        sa.Column("account_number", sa.Text()),
        sa.Column("ifsc_code", sa.String(20)),
        sa.Column("bank_name", sa.String(128)),
        sa.Column("upi_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema="auth",
    )
    op.drop_constraint("chk_payout_owner_type", "payout_requests", schema="subscription", type_="check")
    op.create_check_constraint(
        "chk_payout_owner_type", "payout_requests", "owner_type IN ('provider', 'delivery_boy', 'customer')",
        schema="subscription",
    )


def downgrade() -> None:
    op.drop_constraint("chk_payout_owner_type", "payout_requests", schema="subscription", type_="check")
    op.create_check_constraint(
        "chk_payout_owner_type", "payout_requests", "owner_type IN ('provider', 'delivery_boy')", schema="subscription",
    )
    op.drop_table("user_payout_details", schema="auth")
