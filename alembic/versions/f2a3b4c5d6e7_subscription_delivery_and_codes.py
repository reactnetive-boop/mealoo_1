"""subscription delivery assignment, daily kitchen pickup codes, delivery codes
derived from a seed, ready_for_pickup / picked_up order steps

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-04 00:00:00.000000

Data handling:
- Every order gets a random delivery_code_seed; the customer's 6-digit code is
  derived from it with a server key, so the plaintext otp_for_delivery column
  is cleared. Customers holding today's code see a new one after the upgrade.
- The per-order 4-digit pickup_code is retired (kitchens now have one code per
  day) and cleared.
- Order statuses need no data change: 'ready_for_pickup' and 'picked_up' are
  new values only (status is a plain varchar).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORDER_TABLES = ("orders", "extra_orders")


def upgrade() -> None:

    # ── Subscription -> delivery partner ───────────────────────────
    op.add_column(
        "subscriptions",
        sa.Column("delivery_boy_reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="subscription",
    )
    op.create_foreign_key(
        "subscriptions_delivery_boy_id_fkey", "subscriptions", "delivery_boys",
        ["delivery_boy_reference_id"], ["delivery_boy_id"],
        source_schema="subscription", referent_schema="delivery",
    )
    op.create_index(
        "idx_subscriptions_delivery_boy", "subscriptions", ["delivery_boy_reference_id"], schema="subscription",
    )

    op.create_table(
        "subscription_delivery_assignments",
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "subscription_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription.subscriptions.subscription_id", name="sub_assignments_subscription_id_fkey"),
            nullable=False,
        ),
        sa.Column(
            "delivery_boy_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery.delivery_boys.delivery_boy_id", name="sub_assignments_delivery_boy_id_fkey"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_by_type", sa.String(20), nullable=False, server_default="admin"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("orders_assigned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ended_by_type", sa.String(20), nullable=True),
        sa.Column("end_reason", sa.String(50), nullable=True),
        sa.CheckConstraint("status IN ('active', 'ended')", name="chk_sub_assignment_status"),
        schema="subscription",
    )
    op.create_index(
        "idx_sub_assignments_subscription", "subscription_delivery_assignments",
        ["subscription_reference_id"], schema="subscription",
    )
    op.create_index(
        "idx_sub_assignments_delivery_boy", "subscription_delivery_assignments",
        ["delivery_boy_reference_id", "status"], schema="subscription",
    )
    op.create_index(
        "uq_sub_assignment_active", "subscription_delivery_assignments",
        ["subscription_reference_id"], unique=True, schema="subscription",
        postgresql_where=sa.text("status = 'active'"),
    )

    # ── Kitchen daily pickup codes ─────────────────────────────────
    op.create_table(
        "provider_pickup_codes",
        sa.Column("pickup_code_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider.providers.provider_id", name="provider_pickup_codes_provider_id_fkey"),
            nullable=False,
        ),
        sa.Column("code_date", sa.Date(), nullable=False),
        sa.Column("code_seed", sa.String(64), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_type", sa.String(20), nullable=False, server_default="system"),
        sa.Column("regenerated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("provider_reference_id", "code_date", name="uq_provider_pickup_code_day"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="chk_pickup_code_status"),
        schema="provider",
    )

    # ── Orders: verification attempts, seeds, hand-over timestamps ─
    for table in ORDER_TABLES:
        op.add_column(table, sa.Column("pickup_code_attempts", sa.SmallInteger(), nullable=False, server_default="0"), schema="subscription")
        op.add_column(table, sa.Column("delivery_code_seed", sa.String(64), nullable=True), schema="subscription")
        op.add_column(table, sa.Column("out_for_delivery_at", sa.DateTime(timezone=True), nullable=True), schema="subscription")
        op.add_column(table, sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True), schema="subscription")
        # 128-bit random seed per row; plaintext codes are no longer kept
        op.execute(f"""
            UPDATE subscription.{table}
               SET delivery_code_seed = md5(gen_random_uuid()::text || clock_timestamp()::text),
                   otp_for_delivery = NULL,
                   pickup_code = NULL
        """)

    op.create_index(
        "idx_orders_delivery_boy_date", "orders", ["delivery_boy_reference_id", "order_date"], schema="subscription",
    )
    op.create_index(
        "idx_extra_orders_delivery_boy_date", "extra_orders", ["delivery_boy_reference_id", "delivery_date"],
        schema="subscription",
    )


def downgrade() -> None:
    op.drop_index("idx_extra_orders_delivery_boy_date", table_name="extra_orders", schema="subscription")
    op.drop_index("idx_orders_delivery_boy_date", table_name="orders", schema="subscription")

    # The previous release stores plaintext codes: give open orders fresh ones
    # and move statuses it does not know back to the nearest one it does.
    rand = "(('x' || substr(md5(gen_random_uuid()::text), 1, 8))::bit(32)::bigint)"
    op.execute(f"""
        UPDATE subscription.orders
           SET otp_for_delivery = lpad(({rand} % 1000000)::text, 6, '0'),
               pickup_code = lpad(({rand} % 10000)::text, 4, '0')
         WHERE status NOT IN ('delivered', 'skipped', 'cancelled')
    """)
    op.execute(f"""
        UPDATE subscription.extra_orders
           SET otp_for_delivery = lpad(({rand} % 1000000)::text, 6, '0'),
               pickup_code = lpad(({rand} % 10000)::text, 4, '0')
         WHERE status NOT IN ('delivered', 'cancelled')
    """)
    for table in ORDER_TABLES:
        op.execute(f"UPDATE subscription.{table} SET status = 'preparing' WHERE status = 'ready_for_pickup'")
        op.execute(f"UPDATE subscription.{table} SET status = 'out_for_delivery' WHERE status = 'picked_up'")
        for col in ("arrived_at", "out_for_delivery_at", "delivery_code_seed", "pickup_code_attempts"):
            op.drop_column(table, col, schema="subscription")

    op.drop_table("provider_pickup_codes", schema="provider")

    op.drop_index("uq_sub_assignment_active", table_name="subscription_delivery_assignments", schema="subscription")
    op.drop_index("idx_sub_assignments_delivery_boy", table_name="subscription_delivery_assignments", schema="subscription")
    op.drop_index("idx_sub_assignments_subscription", table_name="subscription_delivery_assignments", schema="subscription")
    op.drop_table("subscription_delivery_assignments", schema="subscription")

    op.drop_index("idx_subscriptions_delivery_boy", table_name="subscriptions", schema="subscription")
    op.drop_constraint("subscriptions_delivery_boy_id_fkey", "subscriptions", schema="subscription", type_="foreignkey")
    op.drop_column("subscriptions", "delivery_boy_reference_id", schema="subscription")
