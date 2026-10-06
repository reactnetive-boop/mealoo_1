"""package revisions: edits to a live package wait for review

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("menu_packages", sa.Column("pending_changes", postgresql.JSONB(), nullable=True), schema="master")
    op.add_column(
        "menu_packages", sa.Column("pending_changes_at", sa.TIMESTAMP(timezone=True), nullable=True), schema="master",
    )
    op.create_index(
        "idx_menu_packages_pending_changes", "menu_packages", ["pending_changes_at"], schema="master",
        postgresql_where=sa.text("pending_changes IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_menu_packages_pending_changes", table_name="menu_packages", schema="master")
    op.drop_column("menu_packages", "pending_changes_at", schema="master")
    op.drop_column("menu_packages", "pending_changes", schema="master")
