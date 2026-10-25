"""vendor holidays (casual + emergency), skip wallet ledger, price breakup support

* provider.vendor_holidays: one row per holiday declaration. Casual holidays
  are rules (every Sunday, selected weekdays, specific dates, a date range,
  days of the month); an emergency holiday is one date. Rows are never
  deleted: a removed rule keeps its row (status 'removed', or end_date cut to
  the removal day when part of it is already in the past), so the history is
  complete. One active emergency per kitchen and date (partial unique index).
  Existing provider.provider_unavailability dates are copied in as casual
  single-date holidays; that table is left untouched (no longer read) so a
  downgrade loses nothing.
* provider.vendor_holiday_meals: every meal an emergency holiday affected and
  what happened to it (moved to a replacement kitchen, or compensated with
  one extra skip + the meal's value in the wallet), with the wallet and skip
  transaction references and processing / compensation / notification
  status. Unique per (holiday, meal): a meal is processed once per holiday.
* subscription.skip_credit_transactions: the skip wallet ledger (extra free
  skips granted to a subscription), idempotency key unique.
* subscription.orders: original kitchen, replacement package and the holiday
  that changed the meal; vendor + date index for kitchen day lookups.
* subscription.subscriptions.holiday_dates: kitchen holidays inside the
  subscription's span (no meal and no charge on those days).
* auth.notifications.dedupe_key: one customer notice per business event.
* master.pricing_components: a GST row (5%, switched off) so admins can turn
  tax on; taxes are shown as their own lines in every price breakup.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-10-25 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid(name: str, fk: str | None = None, nullable: bool = True, fk_name: str | None = None) -> sa.Column:
    args = [sa.ForeignKey(fk, name=fk_name)] if fk else []
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "vendor_holidays",
        sa.Column("vendor_holiday_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        _uuid("provider_reference_id", "provider.providers.provider_id", False, "vendor_holidays_provider_id_fkey"),
        sa.Column("holiday_type", sa.String(20), nullable=False),
        sa.Column("rule_type", sa.String(20), nullable=False),
        sa.Column("weekdays", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("month_days", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("dates", postgresql.ARRAY(sa.Date()), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("processing_status", sa.String(30), nullable=False, server_default="not_required"),
        sa.Column("affected_meals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replaced_meals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("compensated_meals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_meals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("affected_subscriptions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_type", sa.String(20), nullable=False, server_default="provider"),
        _uuid("created_by"),
        _uuid("updated_by"),
        _uuid("removed_by"),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_reason", sa.Text(), nullable=True),
        _uuid("replaces_holiday_id"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("holiday_type IN ('casual', 'emergency')", name="chk_vendor_holiday_type"),
        sa.CheckConstraint("rule_type IN ('weekly', 'dates', 'range', 'monthly')", name="chk_vendor_holiday_rule"),
        sa.CheckConstraint("status IN ('active', 'removed')", name="chk_vendor_holiday_status"),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="chk_vendor_holiday_dates"),
        schema="provider",
    )
    op.create_index(
        "idx_vendor_holidays_provider_dates", "vendor_holidays",
        ["provider_reference_id", "start_date", "end_date"], schema="provider",
    )
    op.create_index("idx_vendor_holidays_type_date", "vendor_holidays", ["holiday_type", "start_date"], schema="provider")
    op.create_index(
        "uq_vendor_holidays_emergency_day", "vendor_holidays", ["provider_reference_id", "start_date"],
        unique=True, schema="provider",
        postgresql_where=sa.text("holiday_type = 'emergency' AND status = 'active'"),
    )

    op.create_table(
        "vendor_holiday_meals",
        sa.Column("vendor_holiday_meal_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        _uuid("vendor_holiday_reference_id", "provider.vendor_holidays.vendor_holiday_id", False,
              "vendor_holiday_meals_holiday_id_fkey"),
        _uuid("order_reference_id", "subscription.orders.order_id", False, "vendor_holiday_meals_order_id_fkey"),
        _uuid("subscription_reference_id", "subscription.subscriptions.subscription_id", False,
              "vendor_holiday_meals_subscription_id_fkey"),
        _uuid("user_reference_id", "auth.users.user_id", False, "vendor_holiday_meals_user_id_fkey"),
        _uuid("original_vendor_reference_id", "provider.providers.provider_id", False,
              "vendor_holiday_meals_vendor_id_fkey"),
        sa.Column("meal_date", sa.Date(), nullable=False),
        sa.Column("meal_slot", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False, server_default="pending"),
        _uuid("replacement_vendor_reference_id", "provider.providers.provider_id", True,
              "vendor_holiday_meals_replacement_vendor_id_fkey"),
        _uuid("replacement_package_reference_id", "master.menu_packages.package_id", True,
              "vendor_holiday_meals_replacement_package_id_fkey"),
        sa.Column("original_meal_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("replacement_meal_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("meal_amount", sa.Numeric(10, 2), nullable=True),
        _uuid("wallet_transaction_reference_id"),
        _uuid("skip_credit_reference_id"),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("compensation_status", sa.String(20), nullable=False, server_default="not_required"),
        sa.Column("notification_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("notification_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("vendor_holiday_reference_id", "order_reference_id", name="uq_vendor_holiday_meal"),
        sa.CheckConstraint(
            "outcome IN ('pending', 'replaced', 'compensated', 'not_affected', 'failed')",
            name="chk_vendor_holiday_meal_outcome",
        ),
        schema="provider",
    )
    op.create_index("idx_vendor_holiday_meals_order", "vendor_holiday_meals", ["order_reference_id"], schema="provider")
    op.create_index(
        "idx_vendor_holiday_meals_status", "vendor_holiday_meals",
        ["processing_status", "notification_status"], schema="provider",
    )

    op.create_table(
        "skip_credit_transactions",
        sa.Column("skip_credit_transaction_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        _uuid("subscription_reference_id", "subscription.subscriptions.subscription_id", False,
              "skip_credit_txn_subscription_id_fkey"),
        _uuid("user_reference_id", "auth.users.user_id", False, "skip_credit_txn_user_id_fkey"),
        _uuid("order_reference_id", "subscription.orders.order_id", True, "skip_credit_txn_order_id_fkey"),
        _uuid("vendor_reference_id", "provider.providers.provider_id", True, "skip_credit_txn_vendor_id_fkey"),
        sa.Column("meal_date", sa.Date(), nullable=True),
        sa.Column("type", sa.String(10), nullable=False, server_default="credit"),
        sa.Column("skips", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(60), nullable=False),
        sa.Column("free_skips_before", sa.SmallInteger(), nullable=False),
        sa.Column("free_skips_after", sa.SmallInteger(), nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=True),
        _uuid("reference_id"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_skip_credit_idempotency"),
        sa.CheckConstraint("skips > 0", name="chk_skip_credit_positive"),
        sa.CheckConstraint("type IN ('credit', 'debit')", name="chk_skip_credit_type"),
        schema="subscription",
    )
    op.create_index(
        "idx_skip_credit_subscription", "skip_credit_transactions", ["subscription_reference_id"],
        schema="subscription",
    )

    op.add_column("orders", _uuid("original_vendor_reference_id", "provider.providers.provider_id", True,
                                  "orders_original_vendor_id_fkey"), schema="subscription")
    op.add_column("orders", _uuid("replacement_package_reference_id", "master.menu_packages.package_id", True,
                                  "orders_replacement_package_id_fkey"), schema="subscription")
    op.add_column("orders", _uuid("vendor_holiday_reference_id", "provider.vendor_holidays.vendor_holiday_id", True,
                                  "orders_vendor_holiday_id_fkey"), schema="subscription")
    op.create_index("idx_orders_vendor_date", "orders", ["vendor_reference_id", "order_date"], schema="subscription")

    op.add_column("subscriptions", sa.Column("holiday_dates", postgresql.JSONB(), nullable=True), schema="subscription")

    op.add_column("notifications", sa.Column("dedupe_key", sa.String(150), nullable=True), schema="auth")
    op.create_index(
        "uq_notifications_dedupe", "notifications", ["dedupe_key"], unique=True, schema="auth",
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )

    # holidays marked before this release become casual single-date holidays
    op.execute("""
        INSERT INTO provider.vendor_holidays
            (provider_reference_id, holiday_type, rule_type, dates, start_date, end_date, reason,
             status, created_by_type, created_at, updated_at)
        SELECT provider_reference_id, 'casual', 'dates', ARRAY[unavailable_date], unavailable_date,
               unavailable_date, reason, 'active', 'migration', COALESCE(created_at, now()), now()
        FROM provider.provider_unavailability
    """)

    # GST, switched off: admins turn it on in Admin -> Pricing
    op.execute("""
        INSERT INTO master.pricing_components
            (pricing_component_id, component_key, label, calc_type, value, applies_to, charge_basis,
             is_customer_facing, is_active, version, change_reason)
        SELECT gen_random_uuid(), 'gst', 'GST', 'percentage', 5, 'all', 'per_order', TRUE, FALSE, 1, 'initial'
        WHERE NOT EXISTS (SELECT 1 FROM master.pricing_components WHERE component_key = 'gst')
    """)


def downgrade() -> None:
    op.execute("DELETE FROM master.pricing_components WHERE component_key = 'gst'")
    op.drop_index("uq_notifications_dedupe", table_name="notifications", schema="auth")
    op.drop_column("notifications", "dedupe_key", schema="auth")
    op.drop_column("subscriptions", "holiday_dates", schema="subscription")
    op.drop_index("idx_orders_vendor_date", table_name="orders", schema="subscription")
    for column in ("vendor_holiday_reference_id", "replacement_package_reference_id", "original_vendor_reference_id"):
        op.drop_column("orders", column, schema="subscription")
    op.drop_index("idx_skip_credit_subscription", table_name="skip_credit_transactions", schema="subscription")
    op.drop_table("skip_credit_transactions", schema="subscription")
    op.drop_index("idx_vendor_holiday_meals_status", table_name="vendor_holiday_meals", schema="provider")
    op.drop_index("idx_vendor_holiday_meals_order", table_name="vendor_holiday_meals", schema="provider")
    op.drop_table("vendor_holiday_meals", schema="provider")
    op.drop_index("uq_vendor_holidays_emergency_day", table_name="vendor_holidays", schema="provider")
    op.drop_index("idx_vendor_holidays_type_date", table_name="vendor_holidays", schema="provider")
    op.drop_index("idx_vendor_holidays_provider_dates", table_name="vendor_holidays", schema="provider")
    op.drop_table("vendor_holidays", schema="provider")
