"""push notification tokens of app installs

Revision ID: b5c6d7e8f9a0
Revises: f0a1b2c3d4e5
Create Date: 2026-10-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_push_tokens",
        sa.Column("device_push_token_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(255), nullable=False, unique=True),
        sa.Column("platform", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("owner_type IN ('customer', 'provider', 'delivery_boy')", name="chk_push_owner_type"),
        schema="auth",
    )
    op.create_index("idx_push_tokens_owner", "device_push_tokens", ["owner_type", "owner_id"], schema="auth")


def downgrade() -> None:
    op.drop_index("idx_push_tokens_owner", table_name="device_push_tokens", schema="auth")
    op.drop_table("device_push_tokens", schema="auth")
