"""kitchen (provider) in-app notifications

Revision ID: a7b8c9d0e1f2
Revises: f2a3b4c5d6e7
Create Date: 2026-10-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_notifications",
        sa.Column("provider_notification_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider.providers.provider_id", name="provider_notifications_provider_id_fkey"),
            nullable=False,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="provider",
    )
    op.create_index("idx_provider_notifications_provider", "provider_notifications", ["provider_reference_id"], schema="provider")
    op.create_index(
        "idx_provider_notifications_unread", "provider_notifications", ["provider_reference_id", "is_read"], schema="provider",
    )


def downgrade() -> None:
    op.drop_index("idx_provider_notifications_unread", table_name="provider_notifications", schema="provider")
    op.drop_index("idx_provider_notifications_provider", table_name="provider_notifications", schema="provider")
    op.drop_table("provider_notifications", schema="provider")
