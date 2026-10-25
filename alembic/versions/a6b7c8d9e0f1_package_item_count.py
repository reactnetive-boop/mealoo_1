"""package items: a plain count without a unit

Kitchens no longer pick units, but they still say how many of an item one
meal has (Roti 4). The count is stored in quantity_value with no unit (label
"4" in `quantity`); items with a unit keep their stored values. Nothing is
dropped.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-10-25 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a6b7c8d9e0f1'
down_revision: Union[str, None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "menu_package_items"
NAME = "chk_package_item_value"
OLD = "(quantity_unit IS NULL AND quantity_value IS NULL) OR (quantity_unit IS NOT NULL AND quantity_value > 0)"
NEW = (
    "(quantity_unit IS NULL AND (quantity_value IS NULL "
    "OR (quantity_value >= 1 AND quantity_value <= 999 AND quantity_value = trunc(quantity_value)))) "
    "OR (quantity_unit IS NOT NULL AND quantity_value > 0)"
)


def upgrade() -> None:
    op.drop_constraint(NAME, TABLE, schema="master", type_="check")
    op.create_check_constraint(NAME, TABLE, NEW, schema="master")


def downgrade() -> None:
    # the count stays readable as the `quantity` label ("4"); only the number column is cleared
    op.execute(f"UPDATE master.{TABLE} SET quantity_value = NULL WHERE quantity_unit IS NULL")
    op.drop_constraint(NAME, TABLE, schema="master", type_="check")
    op.create_check_constraint(NAME, TABLE, OLD, schema="master")
