"""emergency holidays for selected meals; free skip only for kitchens serving two or more meals a day

* provider.vendor_holidays.meal_slots and provider.vendor_holiday_requests.
  meal_slots: the meals (breakfast, lunch, dinner) an emergency holiday
  blocks. NULL = the whole day. Every holiday and request that exists keeps
  NULL, so it stays a full-day closure and behaves exactly as before.
* uq_vendor_holidays_emergency_day (one emergency holiday per kitchen and
  date) is replaced by one partial unique index per meal: two active
  emergency holidays of a kitchen can never block the same meal of the same
  date, and a full-day one takes part in all three.
* provider.vendor_holiday_subscriptions.skip_status may be 'not_eligible':
  a full-day holiday of a kitchen that normally serves fewer than two meals
  a day grants no free skip (its meals are still refunded and the customer
  is still told).

Downgrade is refused while a holiday or request for selected meals, or a
'not_eligible' skip row, exists: the old schema cannot hold them.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-10-27 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SLOTS = ("breakfast", "lunch", "dinner")
SLOTS_CHECK = (
    "meal_slots IS NULL OR (cardinality(meal_slots) >= 1 "
    "AND meal_slots <@ ARRAY['breakfast', 'lunch', 'dinner']::varchar[])"
)
OLD_SKIP_STATUSES = "skip_status IN ('pending', 'completed', 'failed')"
NEW_SKIP_STATUSES = "skip_status IN ('pending', 'completed', 'failed', 'not_eligible')"


def upgrade() -> None:
    for table, check in (("vendor_holidays", "chk_vendor_holiday_meal_slots"),
                         ("vendor_holiday_requests", "chk_holiday_request_meal_slots")):
        op.add_column(table, sa.Column("meal_slots", postgresql.ARRAY(sa.String(20)), nullable=True),
                      schema="provider")
        op.create_check_constraint(check, table, SLOTS_CHECK, schema="provider")

    op.drop_index("uq_vendor_holidays_emergency_day", table_name="vendor_holidays", schema="provider")
    for slot in SLOTS:
        op.create_index(
            f"uq_vendor_holidays_emergency_{slot}", "vendor_holidays", ["provider_reference_id", "start_date"],
            unique=True, schema="provider",
            postgresql_where=sa.text(
                f"holiday_type = 'emergency' AND status = 'active' "
                f"AND (meal_slots IS NULL OR '{slot}' = ANY(meal_slots))"
            ),
        )

    op.drop_constraint("chk_vh_sub_skip_status", "vendor_holiday_subscriptions", schema="provider", type_="check")
    op.create_check_constraint("chk_vh_sub_skip_status", "vendor_holiday_subscriptions", NEW_SKIP_STATUSES,
                               schema="provider")


def downgrade() -> None:
    conn = op.get_bind()
    blocking = conn.execute(sa.text(
        "SELECT (SELECT count(*) FROM provider.vendor_holidays WHERE meal_slots IS NOT NULL) "
        "+ (SELECT count(*) FROM provider.vendor_holiday_requests WHERE meal_slots IS NOT NULL) "
        "+ (SELECT count(*) FROM provider.vendor_holiday_subscriptions WHERE skip_status = 'not_eligible')"
    )).scalar()
    if blocking:
        raise RuntimeError(
            f"{blocking} holiday row(s) use selected meals or 'not_eligible' skips; the old schema cannot hold them"
        )

    op.drop_constraint("chk_vh_sub_skip_status", "vendor_holiday_subscriptions", schema="provider", type_="check")
    op.create_check_constraint("chk_vh_sub_skip_status", "vendor_holiday_subscriptions", OLD_SKIP_STATUSES,
                               schema="provider")

    for slot in SLOTS:
        op.drop_index(f"uq_vendor_holidays_emergency_{slot}", table_name="vendor_holidays", schema="provider")
    op.create_index(
        "uq_vendor_holidays_emergency_day", "vendor_holidays", ["provider_reference_id", "start_date"],
        unique=True, schema="provider",
        postgresql_where=sa.text("holiday_type = 'emergency' AND status = 'active'"),
    )

    for table, check in (("vendor_holiday_requests", "chk_holiday_request_meal_slots"),
                         ("vendor_holidays", "chk_vendor_holiday_meal_slots")):
        op.drop_constraint(check, table, schema="provider", type_="check")
        op.drop_column(table, "meal_slots", schema="provider")
