"""catalogue packages: no owning kitchen; the creating admin has its own column

Catalogue (is_predefined) packages stored the creating admin's id in
menu_packages.provider_id. It now lives in created_by_admin_id and
provider_id is NULL for them (and required for every kitchen package).

Revision ID: b2d3e4f5a6b7
Revises: a1c2e3f4a5b6
Create Date: 2026-10-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b2d3e4f5a6b7'
down_revision: Union[str, None] = 'a1c2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("menu_packages", sa.Column("created_by_admin_id", postgresql.UUID(as_uuid=True)), schema="master")
    op.alter_column("menu_packages", "provider_id", nullable=True, schema="master")
    op.execute(
        "UPDATE master.menu_packages SET created_by_admin_id = provider_id, provider_id = NULL "
        "WHERE is_predefined = TRUE"
    )
    op.create_check_constraint(
        "chk_menu_package_owner", "menu_packages", "is_predefined OR provider_id IS NOT NULL", schema="master",
    )


def downgrade() -> None:
    op.drop_constraint("chk_menu_package_owner", "menu_packages", schema="master", type_="check")
    op.execute(
        "UPDATE master.menu_packages SET provider_id = created_by_admin_id WHERE is_predefined = TRUE"
    )
    op.execute(
        "UPDATE master.menu_packages SET provider_id = gen_random_uuid() WHERE provider_id IS NULL"
    )
    op.alter_column("menu_packages", "provider_id", nullable=False, schema="master")
    op.drop_column("menu_packages", "created_by_admin_id", schema="master")
