"""kitchen holiday requests with admin approval, per-subscription holiday skips, notice log, admin notifications

* provider.vendor_holiday_requests: every emergency / regular (weekly)
  holiday request of a kitchen and its decision (pending, approved,
  rejected, withdrawn, expired), who decided, the note, what the request
  would change when sent (impact) and what approving it did (result). One
  pending request per kitchen and dedupe key (partial unique index), so a
  repeated request is never stored twice. Holidays that already exist stay
  in force: they were in force before approvals existed, so nothing is
  re-decided or reprocessed.
* provider.vendor_holiday_subscriptions: one row per (approved emergency
  holiday, active subscription) - its one extra free skip, the meals of it
  refunded and when the customer's notice was logged. Unique, so a retry
  never grants a second skip.
* provider.holiday_notices: the log of every holiday notice (admins,
  kitchens, customers, delivery partners) with status and attempts; unique
  dedupe key. Failed notices are re-sent from here alone.
* master.admin_notifications: in-app notices for admins, one row per admin.

Nothing existing is changed or dropped.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-10-26 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a6b7c8d9e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid(name: str, fk: str | None = None, nullable: bool = True, fk_name: str | None = None) -> sa.Column:
    args = [sa.ForeignKey(fk, name=fk_name)] if fk else []
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable)


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "vendor_holiday_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        _uuid("provider_reference_id", "provider.providers.provider_id", False,
              "vendor_holiday_requests_provider_id_fkey"),
        sa.Column("request_type", sa.String(20), nullable=False),
        sa.Column("action", sa.String(20), nullable=False, server_default="add"),
        _uuid("target_holiday_id", "provider.vendor_holidays.vendor_holiday_id", True,
              "vendor_holiday_requests_target_fkey"),
        sa.Column("holiday_date", sa.Date(), nullable=True),
        sa.Column("weekdays", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("impact", postgresql.JSONB(), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("resulting_holiday_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        *_stamps(),
        sa.CheckConstraint("request_type IN ('emergency', 'regular')", name="chk_holiday_request_type"),
        sa.CheckConstraint("action IN ('add', 'update', 'remove')", name="chk_holiday_request_action"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'withdrawn', 'expired')",
                           name="chk_holiday_request_status"),
        schema="provider",
    )
    op.create_index("idx_holiday_requests_provider", "vendor_holiday_requests",
                    ["provider_reference_id", "created_at"], schema="provider")
    op.create_index("idx_holiday_requests_status", "vendor_holiday_requests", ["status", "created_at"],
                    schema="provider")
    op.create_index("uq_holiday_requests_pending", "vendor_holiday_requests", ["provider_reference_id", "dedupe_key"],
                    unique=True, schema="provider", postgresql_where=sa.text("status = 'pending'"))

    op.create_table(
        "vendor_holiday_subscriptions",
        sa.Column("vendor_holiday_subscription_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        _uuid("vendor_holiday_reference_id", "provider.vendor_holidays.vendor_holiday_id", False,
              "vendor_holiday_subscriptions_holiday_fkey"),
        _uuid("subscription_reference_id", "subscription.subscriptions.subscription_id", False,
              "vendor_holiday_subscriptions_sub_fkey"),
        _uuid("user_reference_id", "auth.users.user_id", False, "vendor_holiday_subscriptions_user_fkey"),
        sa.Column("skip_credit_reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("skip_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("refunded_meals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refund_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("notice_queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.UniqueConstraint("vendor_holiday_reference_id", "subscription_reference_id",
                            name="uq_vendor_holiday_subscription"),
        sa.CheckConstraint("skip_status IN ('pending', 'completed', 'failed')", name="chk_vh_sub_skip_status"),
        schema="provider",
    )
    op.create_index("idx_vendor_holiday_subscriptions_status", "vendor_holiday_subscriptions", ["skip_status"],
                    schema="provider")

    op.create_table(
        "holiday_notices",
        sa.Column("holiday_notice_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vendor_holiday_reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audience", sa.String(20), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("dedupe_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("dedupe_key", name="uq_holiday_notices_dedupe"),
        sa.CheckConstraint("audience IN ('admin', 'provider', 'customer', 'delivery_boy')",
                           name="chk_holiday_notice_audience"),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name="chk_holiday_notice_status"),
        schema="provider",
    )
    op.create_index("idx_holiday_notices_status", "holiday_notices", ["status", "created_at"], schema="provider")
    op.create_index("idx_holiday_notices_holiday", "holiday_notices", ["vendor_holiday_reference_id"],
                    schema="provider")
    op.create_index("idx_holiday_notices_request", "holiday_notices", ["request_reference_id"], schema="provider")

    op.create_table(
        "admin_notifications",
        sa.Column("admin_notification_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        _uuid("admin_user_reference_id", "master.admin_users.admin_user_id", False,
              "admin_notifications_admin_id_fkey"),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("dedupe_key", sa.String(200), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_admin_notifications_dedupe"),
        schema="master",
    )
    op.create_index("idx_admin_notifications_unread", "admin_notifications",
                    ["admin_user_reference_id", "is_read", "created_at"], schema="master")


def downgrade() -> None:
    op.drop_index("idx_admin_notifications_unread", table_name="admin_notifications", schema="master")
    op.drop_table("admin_notifications", schema="master")
    for name in ("idx_holiday_notices_request", "idx_holiday_notices_holiday", "idx_holiday_notices_status"):
        op.drop_index(name, table_name="holiday_notices", schema="provider")
    op.drop_table("holiday_notices", schema="provider")
    op.drop_index("idx_vendor_holiday_subscriptions_status", table_name="vendor_holiday_subscriptions",
                  schema="provider")
    op.drop_table("vendor_holiday_subscriptions", schema="provider")
    for name in ("uq_holiday_requests_pending", "idx_holiday_requests_status", "idx_holiday_requests_provider"):
        op.drop_index(name, table_name="vendor_holiday_requests", schema="provider")
    op.drop_table("vendor_holiday_requests", schema="provider")
