"""kitchens can deliver to more than their own pincode

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-10-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, None] = 'e9f0a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_service_areas",
        sa.Column("provider_service_area_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider.providers.provider_id", name="provider_service_areas_provider_id_fkey"),
            nullable=False,
        ),
        sa.Column("pincode", sa.Integer(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("provider_reference_id", "pincode", name="uq_provider_service_area"),
        schema="provider",
    )
    op.create_index(
        "ix_provider_provider_service_areas_pincode", "provider_service_areas", ["pincode"], schema="provider",
    )


def downgrade() -> None:
    op.drop_index("ix_provider_provider_service_areas_pincode", table_name="provider_service_areas", schema="provider")
    op.drop_table("provider_service_areas", schema="provider")
