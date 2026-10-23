"""package items: quantity with a unit

menu_package_items.quantity was free text (the kitchen app sent bare counts
like "2"). Items now carry an amount and a unit (g, kg, pcs, bowl, ml, l)
and, for bowls, optionally what one bowl holds (g or ml). `quantity` stays
as the display label ("400 g", "1 bowl (300 g)"); existing rows keep their
text and have no unit until the kitchen edits them.

Revision ID: c3d4e5f6a7b8
Revises: b2d3e4f5a6b7
Create Date: 2026-10-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "menu_package_items"
CHECKS = {
    "chk_package_item_unit": "quantity_unit IS NULL OR quantity_unit IN ('g', 'kg', 'pcs', 'bowl', 'ml', 'l')",
    "chk_package_item_value": (
        "(quantity_unit IS NULL AND quantity_value IS NULL) "
        "OR (quantity_unit IS NOT NULL AND quantity_value > 0)"
    ),
    "chk_package_item_bowl": (
        "(bowl_capacity IS NULL AND bowl_capacity_unit IS NULL) "
        "OR (quantity_unit = 'bowl' AND bowl_capacity > 0 AND bowl_capacity_unit IN ('g', 'ml'))"
    ),
}


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("quantity_value", sa.Numeric(10, 2), nullable=True), schema="master")
    op.add_column(TABLE, sa.Column("quantity_unit", sa.String(10), nullable=True), schema="master")
    op.add_column(TABLE, sa.Column("bowl_capacity", sa.Numeric(10, 2), nullable=True), schema="master")
    op.add_column(TABLE, sa.Column("bowl_capacity_unit", sa.String(5), nullable=True), schema="master")
    for name, condition in CHECKS.items():
        op.create_check_constraint(name, TABLE, condition, schema="master")


def downgrade() -> None:
    for name in CHECKS:
        op.drop_constraint(name, TABLE, schema="master", type_="check")
    for column in ("bowl_capacity_unit", "bowl_capacity", "quantity_unit", "quantity_value"):
        op.drop_column(TABLE, column, schema="master")
