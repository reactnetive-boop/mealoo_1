"""complaints get an admin assignee (SLA tracking)

Revision ID: a1c2e3f4a5b6
Revises: f9a0b1c2d3e4
Create Date: 2026-10-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1c2e3f4a5b6'
down_revision: Union[str, None] = 'f9a0b1c2d3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (("provider", "complaints"), ("provider", "provider_complaints"), ("delivery", "delivery_boy_complaints"))


def upgrade() -> None:
    for schema, table in TABLES:
        op.add_column(table, sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True), schema=schema)
        op.create_index(f"ix_{schema}_{table}_assigned_to", table, ["assigned_to"], schema=schema)


def downgrade() -> None:
    for schema, table in TABLES:
        op.drop_index(f"ix_{schema}_{table}_assigned_to", table_name=table, schema=schema)
        op.drop_column(table, "assigned_to", schema=schema)
