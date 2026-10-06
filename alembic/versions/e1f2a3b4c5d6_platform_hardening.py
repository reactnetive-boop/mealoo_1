"""platform hardening: approvals, token revocation, pricing engine, ledgers,
order codes, payout requests

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-10-02 00:00:00.000000

Data handling:
- Existing kitchens with a completed profile and existing delivery partners
  with a completed profile are grandfathered as 'approved' so live operations
  keep running; everyone else starts 'pending'.
- Existing packages that are active become 'approved'; inactive ones become
  'pending' (they may be drafts or soft-deleted - an admin decides).
- discounted_price is the selling price. Values that are zero, negative or
  not below the price meant "no discount" and become NULL.
- OTPs still in flight are invalidated: the column now stores a keyed hash.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACCOUNT_TABLES = [
    ("auth", "users"),
    ("provider", "providers"),
    ("delivery", "delivery_boys"),
    ("master", "admin_users"),
]


def _add_account_security(schema, table):
    op.add_column(table, sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"), schema=schema)
    op.add_column(table, sa.Column("failed_login_count", sa.SmallInteger(), nullable=False, server_default="0"), schema=schema)
    op.add_column(table, sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True), schema=schema)


def _add_order_codes(table):
    op.add_column(table, sa.Column("delivery_code_attempts", sa.SmallInteger(), nullable=False, server_default="0"), schema="subscription")
    op.add_column(table, sa.Column("pickup_code", sa.String(6), nullable=True), schema="subscription")
    op.add_column(table, sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True), schema="subscription")
    op.add_column(table, sa.Column("cancel_reason", sa.String(50), nullable=True), schema="subscription")
    op.add_column(table, sa.Column("refund_amount", sa.Numeric(10, 2), nullable=True), schema="subscription")
    op.add_column(table, sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True), schema="subscription")
    op.add_column(table, sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True), schema="subscription")


def upgrade() -> None:

    # ── Accounts: token revocation + login lockout ─────────────────
    for schema, table in ACCOUNT_TABLES:
        _add_account_security(schema, table)

    # ── Kitchen approval ───────────────────────────────────────────
    op.add_column("providers", sa.Column("approval_status", sa.String(20), nullable=False, server_default="pending"), schema="provider")
    op.add_column("providers", sa.Column("approval_note", sa.Text(), nullable=True), schema="provider")
    op.add_column("providers", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True), schema="provider")
    op.add_column("providers", sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True), schema="provider")
    op.execute("""
        UPDATE provider.providers
           SET approval_status = 'approved', approved_at = now()
         WHERE is_profile_completed IS TRUE
    """)
    op.create_check_constraint(
        "chk_provider_approval_status", "providers",
        "approval_status IN ('pending', 'approved', 'rejected')", schema="provider",
    )

    # ── Delivery partner approval + document review ────────────────
    op.add_column("delivery_boys", sa.Column("approval_status", sa.String(20), nullable=False, server_default="pending"), schema="delivery")
    op.add_column("delivery_boys", sa.Column("approval_note", sa.Text(), nullable=True), schema="delivery")
    op.add_column("delivery_boys", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True), schema="delivery")
    op.add_column("delivery_boys", sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True), schema="delivery")
    op.execute("""
        UPDATE delivery.delivery_boys
           SET approval_status = 'approved', approved_at = now()
         WHERE full_name IS NOT NULL AND vehicle_type IS NOT NULL
    """)
    op.create_check_constraint(
        "chk_delivery_boy_approval_status", "delivery_boys",
        "approval_status IN ('pending', 'approved', 'rejected')", schema="delivery",
    )
    op.add_column("delivery_boy_documents", sa.Column("remarks", sa.Text(), nullable=True), schema="delivery")
    op.add_column("delivery_boy_documents", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True), schema="delivery")
    op.add_column("delivery_boy_documents", sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True), schema="delivery")

    # ── OTP storage: keyed hashes, purposes, reset tokens ──────────
    op.execute("UPDATE provider.otp_logs SET is_verified = TRUE, expires_at = LEAST(expires_at, now())")
    op.execute("UPDATE provider.otp_logs SET attempts = 0 WHERE attempts IS NULL")
    op.alter_column("otp_logs", "attempts", existing_type=sa.Integer(), nullable=False, server_default="0", schema="provider")
    op.add_column("otp_logs", sa.Column("reset_token_hash", sa.Text(), nullable=True), schema="provider")
    op.add_column("otp_logs", sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True), schema="provider")

    op.execute("UPDATE auth.otp_logs SET is_used = TRUE, expires_at = LEAST(expires_at, now())")
    op.add_column("otp_logs", sa.Column("reset_token_hash", sa.Text(), nullable=True), schema="auth")
    op.add_column("otp_logs", sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True), schema="auth")

    op.alter_column("delivery_boy_otp_logs", "otp", existing_type=sa.String(6), type_=sa.Text(), schema="delivery")
    op.execute("UPDATE delivery.delivery_boy_otp_logs SET is_verified = TRUE, expires_at = LEAST(expires_at, now())")
    op.execute("UPDATE delivery.delivery_boy_otp_logs SET attempts = 0 WHERE attempts IS NULL")
    op.alter_column("delivery_boy_otp_logs", "attempts", existing_type=sa.Integer(), nullable=False, server_default="0", schema="delivery")
    op.add_column("delivery_boy_otp_logs", sa.Column("purpose", sa.String(30), nullable=False, server_default="registration"), schema="delivery")
    op.add_column("delivery_boy_otp_logs", sa.Column("reset_token_hash", sa.Text(), nullable=True), schema="delivery")
    op.add_column("delivery_boy_otp_logs", sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True), schema="delivery")

    # ── Packages: approval, soft delete, unambiguous prices ────────
    op.add_column("menu_packages", sa.Column("approval_status", sa.String(20), nullable=False, server_default="pending"), schema="master")
    op.add_column("menu_packages", sa.Column("approval_note", sa.Text(), nullable=True), schema="master")
    op.add_column("menu_packages", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True), schema="master")
    op.add_column("menu_packages", sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True), schema="master")
    op.add_column("menu_packages", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), schema="master")
    op.execute("""
        UPDATE master.menu_packages
           SET approval_status = 'approved', approved_at = now()
         WHERE is_active IS TRUE
    """)
    op.execute("""
        UPDATE master.menu_packages
           SET discounted_price = NULL
         WHERE discounted_price IS NOT NULL
           AND (discounted_price <= 0 OR discounted_price >= price)
    """)
    op.execute("UPDATE master.menu_packages SET subscription_price = NULL WHERE subscription_price <= 0")
    op.create_check_constraint("chk_package_approval_status", "menu_packages",
                               "approval_status IN ('pending', 'approved', 'rejected')", schema="master")
    op.create_check_constraint("chk_package_price_positive", "menu_packages", "price > 0", schema="master")
    op.create_check_constraint(
        "chk_package_selling_price", "menu_packages",
        "discounted_price IS NULL OR (discounted_price > 0 AND discounted_price <= price)", schema="master",
    )
    op.create_check_constraint(
        "chk_package_subscription_price", "menu_packages",
        "subscription_price IS NULL OR subscription_price > 0", schema="master",
    )
    op.create_index("idx_menu_packages_approval", "menu_packages", ["approval_status"], schema="master")

    # ── Pricing configuration (versioned) ─────────────────────────
    op.create_table(
        "pricing_components",
        sa.Column("pricing_component_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("component_key", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("calc_type", sa.String(20), nullable=False),
        sa.Column("value", sa.Numeric(10, 2), nullable=False),
        sa.Column("applies_to", sa.String(20), nullable=False, server_default="all"),
        sa.Column("charge_basis", sa.String(20), nullable=False, server_default="per_order"),
        sa.Column("is_customer_facing", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("value >= 0", name="chk_pricing_value_non_negative"),
        sa.CheckConstraint("calc_type IN ('fixed', 'percentage')", name="chk_pricing_calc_type"),
        sa.CheckConstraint("applies_to IN ('all', 'subscription', 'extra_order')", name="chk_pricing_applies_to"),
        sa.CheckConstraint("charge_basis IN ('per_unit', 'per_delivery', 'per_order')", name="chk_pricing_basis"),
        schema="master",
    )
    op.create_index(
        "uq_pricing_component_current", "pricing_components", ["component_key"],
        unique=True, schema="master", postgresql_where=sa.text("superseded_at IS NULL"),
    )
    # Everything starts at zero so prices do not change until an admin sets
    # them; the partner payout keeps today's flat fee.
    op.execute("""
        INSERT INTO master.pricing_components
            (pricing_component_id, component_key, label, calc_type, value, applies_to,
             charge_basis, is_customer_facing, is_active, version, change_reason)
        VALUES
            (gen_random_uuid(), 'sms_charge', 'SMS Charge', 'fixed', 0, 'all', 'per_order', TRUE, TRUE, 1, 'initial'),
            (gen_random_uuid(), 'payment_gateway_charge', 'Payment Gateway Charge', 'percentage', 0, 'all', 'per_order', TRUE, TRUE, 1, 'initial'),
            (gen_random_uuid(), 'packaging_charge', 'Packaging / Shipping', 'fixed', 0, 'all', 'per_unit', TRUE, TRUE, 1, 'initial'),
            (gen_random_uuid(), 'delivery_charge', 'Delivery Charge', 'fixed', 0, 'all', 'per_delivery', TRUE, TRUE, 1, 'initial'),
            (gen_random_uuid(), 'platform_commission', 'Orleeno Commission', 'percentage', 0, 'all', 'per_order', TRUE, TRUE, 1, 'initial'),
            (gen_random_uuid(), 'delivery_partner_payout', 'Delivery Partner Payout', 'fixed', 30, 'all', 'per_delivery', FALSE, TRUE, 1, 'initial')
    """)

    # ── Subscriptions: charges, frozen pricing, refunds ────────────
    op.add_column("subscriptions", sa.Column("charges_amount", sa.Numeric(10, 2), nullable=False, server_default="0"), schema="subscription")
    op.add_column("subscriptions", sa.Column("pricing_snapshot", postgresql.JSONB(), nullable=True), schema="subscription")
    op.add_column("subscriptions", sa.Column("refunded_amount", sa.Numeric(10, 2), nullable=False, server_default="0"), schema="subscription")

    # ── Orders: codes, reasons, refund / settlement markers ────────
    _add_order_codes("orders")
    _add_order_codes("extra_orders")
    op.add_column("extra_orders", sa.Column("otp_for_delivery", sa.String(6), nullable=True), schema="subscription")
    op.add_column("extra_orders", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True), schema="subscription")
    op.add_column("extra_orders", sa.Column("checkout_id", postgresql.UUID(as_uuid=True), nullable=True), schema="subscription")
    op.add_column("extra_orders", sa.Column("charges_amount", sa.Numeric(10, 2), nullable=False, server_default="0"), schema="subscription")
    op.add_column("extra_orders", sa.Column("pricing_snapshot", postgresql.JSONB(), nullable=True), schema="subscription")
    op.create_index("ix_subscription_extra_orders_checkout_id", "extra_orders", ["checkout_id"], schema="subscription")
    op.create_index("idx_extra_orders_vendor_date", "extra_orders", ["vendor_reference_id", "delivery_date", "meal_slot"], schema="subscription")
    op.create_index("idx_orders_vendor_date_slot", "orders", ["vendor_reference_id", "order_date", "meal_slot"], schema="subscription")
    # Orders that were delivered already have their earnings booked
    op.execute("UPDATE subscription.orders SET settled_at = COALESCE(delivered_at, updated_at) WHERE status = 'delivered'")
    op.execute("UPDATE subscription.extra_orders SET settled_at = updated_at WHERE status = 'delivered'")
    # Open orders get fresh codes from a strong random source (gen_random_uuid):
    # a kitchen pickup code they never had, and a new customer delivery code,
    # because the old subscription delivery codes were visible in the kitchen app.
    rand = "(('x' || substr(md5(gen_random_uuid()::text), 1, 8))::bit(32)::bigint)"
    op.execute(f"""
        UPDATE subscription.orders
           SET otp_for_delivery = lpad(({rand} % 1000000)::text, 6, '0'),
               pickup_code = lpad(({rand} % 10000)::text, 4, '0')
         WHERE status IN ('scheduled', 'preparing', 'out_for_delivery')
    """)
    op.execute(f"""
        UPDATE subscription.extra_orders
           SET otp_for_delivery = lpad(({rand} % 1000000)::text, 6, '0'),
               pickup_code = lpad(({rand} % 10000)::text, 4, '0')
         WHERE status IN ('pending', 'confirmed', 'preparing', 'out_for_delivery')
    """)

    # ── Idempotency keys on every ledger ───────────────────────────
    for schema, table, name in (
        ("subscription", "wallet_transactions", "wallet_transactions_idempotency_key_key"),
        ("provider", "provider_wallet_transactions", "provider_wallet_transactions_idempotency_key_key"),
        ("delivery", "delivery_boy_wallet_transactions", "delivery_boy_wallet_transactions_idempotency_key_key"),
        ("subscription", "payments", "payments_idempotency_key_key"),
    ):
        op.add_column(table, sa.Column("idempotency_key", sa.String(120), nullable=True), schema=schema)
        op.create_unique_constraint(name, table, ["idempotency_key"], schema=schema)

    # ── Platform ledger ────────────────────────────────────────────
    op.create_table(
        "platform_ledger_entries",
        sa.Column("platform_ledger_entry_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_type", sa.String(40), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="chk_platform_ledger_amount"),
        sa.CheckConstraint("direction IN ('credit', 'debit')", name="chk_platform_ledger_direction"),
        sa.UniqueConstraint("idempotency_key", name="platform_ledger_entries_idempotency_key_key"),
        schema="subscription",
    )
    op.create_index("idx_platform_ledger_reference", "platform_ledger_entries", ["reference_type", "reference_id"], schema="subscription")
    op.create_index("idx_platform_ledger_type", "platform_ledger_entries", ["entry_type"], schema="subscription")

    # ── Withdrawal requests (kitchens and delivery partners) ───────
    op.create_table(
        "payout_requests",
        sa.Column("payout_request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("payout_reference", sa.String(120), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="chk_payout_request_amount"),
        sa.CheckConstraint("owner_type IN ('provider', 'delivery_boy')", name="chk_payout_owner_type"),
        sa.CheckConstraint("status IN ('pending', 'paid', 'rejected')", name="chk_payout_status"),
        schema="subscription",
    )
    op.create_index("idx_payout_requests_owner", "payout_requests", ["owner_type", "owner_id"], schema="subscription")
    op.create_index("idx_payout_requests_status", "payout_requests", ["status"], schema="subscription")

    # ── Audit log: the table is partitioned but had no partition, so every
    # insert failed. A default partition makes it usable.
    op.execute("CREATE TABLE IF NOT EXISTS master.audit_logs_default PARTITION OF master.audit_logs DEFAULT")

    # ── Subscription status now includes expiry ───────────────────
    op.execute("""
        UPDATE subscription.subscriptions
           SET status = 'expired'
         WHERE status = 'active' AND end_date <= (now() AT TIME ZONE 'Asia/Kolkata')::date
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS master.audit_logs_default")

    op.drop_index("idx_payout_requests_status", table_name="payout_requests", schema="subscription")
    op.drop_index("idx_payout_requests_owner", table_name="payout_requests", schema="subscription")
    op.drop_table("payout_requests", schema="subscription")

    op.drop_index("idx_platform_ledger_type", table_name="platform_ledger_entries", schema="subscription")
    op.drop_index("idx_platform_ledger_reference", table_name="platform_ledger_entries", schema="subscription")
    op.drop_table("platform_ledger_entries", schema="subscription")

    for schema, table, name in (
        ("subscription", "wallet_transactions", "wallet_transactions_idempotency_key_key"),
        ("provider", "provider_wallet_transactions", "provider_wallet_transactions_idempotency_key_key"),
        ("delivery", "delivery_boy_wallet_transactions", "delivery_boy_wallet_transactions_idempotency_key_key"),
        ("subscription", "payments", "payments_idempotency_key_key"),
    ):
        op.drop_constraint(name, table, schema=schema, type_="unique")
        op.drop_column(table, "idempotency_key", schema=schema)

    op.drop_index("idx_orders_vendor_date_slot", table_name="orders", schema="subscription")
    op.drop_index("idx_extra_orders_vendor_date", table_name="extra_orders", schema="subscription")
    op.drop_index("ix_subscription_extra_orders_checkout_id", table_name="extra_orders", schema="subscription")
    for col in ("pricing_snapshot", "charges_amount", "checkout_id", "delivered_at", "otp_for_delivery"):
        op.drop_column("extra_orders", col, schema="subscription")
    for table in ("orders", "extra_orders"):
        for col in ("settled_at", "refunded_at", "refund_amount", "cancel_reason", "picked_up_at",
                    "pickup_code", "delivery_code_attempts"):
            op.drop_column(table, col, schema="subscription")

    for col in ("refunded_amount", "pricing_snapshot", "charges_amount"):
        op.drop_column("subscriptions", col, schema="subscription")

    op.drop_index("uq_pricing_component_current", table_name="pricing_components", schema="master")
    op.drop_table("pricing_components", schema="master")

    op.drop_index("idx_menu_packages_approval", table_name="menu_packages", schema="master")
    for name in ("chk_package_subscription_price", "chk_package_selling_price",
                 "chk_package_price_positive", "chk_package_approval_status"):
        op.drop_constraint(name, "menu_packages", schema="master", type_="check")
    for col in ("deleted_at", "approved_by", "approved_at", "approval_note", "approval_status"):
        op.drop_column("menu_packages", col, schema="master")

    for col in ("reset_token_expires_at", "reset_token_hash", "purpose"):
        op.drop_column("delivery_boy_otp_logs", col, schema="delivery")
    for schema in ("auth", "provider"):
        op.drop_column("otp_logs", "reset_token_expires_at", schema=schema)
        op.drop_column("otp_logs", "reset_token_hash", schema=schema)

    for col in ("verified_by", "verified_at", "remarks"):
        op.drop_column("delivery_boy_documents", col, schema="delivery")
    op.drop_constraint("chk_delivery_boy_approval_status", "delivery_boys", schema="delivery", type_="check")
    for col in ("approved_by", "approved_at", "approval_note", "approval_status"):
        op.drop_column("delivery_boys", col, schema="delivery")
    op.drop_constraint("chk_provider_approval_status", "providers", schema="provider", type_="check")
    for col in ("approved_by", "approved_at", "approval_note", "approval_status"):
        op.drop_column("providers", col, schema="provider")

    for schema, table in ACCOUNT_TABLES:
        for col in ("locked_until", "failed_login_count", "token_version"):
            op.drop_column(table, col, schema=schema)
