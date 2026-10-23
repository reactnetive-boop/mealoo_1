"""kitchens per delivery partner, package ratings, skip notices, plan terms

* delivery.delivery_partner_vendors: a delivery partner can serve several
  kitchens; a kitchen has at most one current partner (partial unique index).
  History is kept (rows are ended, never overwritten). The old single
  delivery_boys.assigned_provider_reference_id is copied in; when several
  partners were dedicated to the same kitchen, the active + approved, most
  recently updated one keeps it and the others are ended
  ("migration_duplicate_kitchen"). The old column is left untouched (it is
  no longer read) so a downgrade can restore it.
* provider.reviews: ratings belong to a package. Reviews without a package get
  it from their one-time order, or from a single-package subscription.
  Subscription reviews without a meal are linked to the delivered meal of
  their review date. The one-review-per-kitchen-per-day index is replaced by
  one visible review per one-time order and per subscription meal; older
  duplicates of the same order are hidden (kept, not deleted).
* provider.provider_notifications.dedupe_key: one notice per business event
  (e.g. one "meal skipped" per meal) even when a request is retried.
* master.subscription_plans: monthly, quarterly and yearly plans get the 5%
  subscription discount; every plan type in use gets the missing meal
  combinations (breakfast + lunch, lunch + dinner, breakfast + dinner, all
  three) with the same days, free skips and discount as the type's plan.
  Plan data changes are not reverted on downgrade.

Revision ID: e4f5a6b7c8d9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-24 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLAN_SLOTS = ("breakfast", "lunch", "dinner", "breakfast_lunch", "lunch_dinner", "breakfast_dinner", "all_slots")
SLOT_ALIASES = {
    "all": "all_slots", "all_day": "all_slots", "full_day": "all_slots",
    "lunch_breakfast": "breakfast_lunch", "dinner_lunch": "lunch_dinner", "dinner_breakfast": "breakfast_dinner",
}
FIVE_PERCENT_TYPES = ("monthly", "quarterly", "yearly", "annually", "annual")


def _vendor_assignments() -> None:
    op.create_table(
        "delivery_partner_vendors",
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "delivery_boy_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery.delivery_boys.delivery_boy_id", name="partner_vendors_delivery_boy_id_fkey"),
            nullable=False,
        ),
        sa.Column(
            "provider_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provider.providers.provider_id", name="partner_vendors_provider_id_fkey"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_by_type", sa.String(20), nullable=False, server_default="admin"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ended_by_type", sa.String(20), nullable=True),
        sa.Column("end_reason", sa.String(50), nullable=True),
        sa.CheckConstraint("status IN ('active', 'ended')", name="chk_partner_vendor_status"),
        schema="delivery",
    )
    op.create_index(
        "idx_partner_vendors_partner", "delivery_partner_vendors", ["delivery_boy_reference_id", "status"],
        schema="delivery",
    )
    op.create_index(
        "idx_partner_vendors_provider", "delivery_partner_vendors", ["provider_reference_id"], schema="delivery",
    )
    # one current partner per kitchen (auto-assignment needs exactly one)
    op.create_index(
        "uq_partner_vendor_active_kitchen", "delivery_partner_vendors", ["provider_reference_id"],
        unique=True, schema="delivery", postgresql_where=sa.text("status = 'active'"),
    )
    op.execute("""
        INSERT INTO delivery.delivery_partner_vendors
            (assignment_id, delivery_boy_reference_id, provider_reference_id, status, assigned_by_type,
             assigned_at, note, ended_at, ended_by_type, end_reason)
        SELECT gen_random_uuid(), b.delivery_boy_id, b.assigned_provider_reference_id,
               CASE WHEN b.rn = 1 THEN 'active' ELSE 'ended' END,
               'system', COALESCE(b.updated_at, now()),
               'Migrated from the single-kitchen assignment',
               CASE WHEN b.rn = 1 THEN NULL ELSE now() END,
               CASE WHEN b.rn = 1 THEN NULL ELSE 'system' END,
               CASE WHEN b.rn = 1 THEN NULL ELSE 'migration_duplicate_kitchen' END
          FROM (
            SELECT d.*, row_number() OVER (
                       PARTITION BY d.assigned_provider_reference_id
                       ORDER BY (d.is_active AND d.approval_status = 'approved') DESC, d.updated_at DESC NULLS LAST
                   ) AS rn
              FROM delivery.delivery_boys d
             WHERE d.assigned_provider_reference_id IS NOT NULL
          ) b
    """)


def _package_reviews() -> None:
    # the package of a one-time order review
    op.execute("""
        UPDATE provider.reviews r
           SET package_reference_id = e.package_reference_id
          FROM subscription.extra_orders e
         WHERE r.package_reference_id IS NULL AND r.order_reference_id = e.extra_order_id
    """)
    # the package of a single-package subscription review
    op.execute("""
        UPDATE provider.reviews r
           SET package_reference_id = sp.package_id
          FROM (
            SELECT subscription_reference_id AS subscription_id, (array_agg(package_reference_id))[1] AS package_id
              FROM subscription.subscription_packages
             GROUP BY subscription_reference_id
            HAVING count(DISTINCT package_reference_id) = 1
          ) sp
         WHERE r.package_reference_id IS NULL AND r.subscription_reference_id = sp.subscription_id
    """)
    # a subscription review rated the meal delivered on its review date
    op.execute("""
        UPDATE provider.reviews r
           SET subscription_order_reference_id = m.order_id
          FROM (
            SELECT DISTINCT ON (o.subscription_reference_id, o.order_date) o.subscription_reference_id AS subscription_id,
                   o.order_date, o.order_id
              FROM subscription.orders o
             WHERE o.status = 'delivered'
             ORDER BY o.subscription_reference_id, o.order_date,
                      CASE o.meal_slot WHEN 'breakfast' THEN 0 WHEN 'lunch' THEN 1 ELSE 2 END
          ) m
         WHERE r.subscription_order_reference_id IS NULL AND r.order_reference_id IS NULL
           AND r.subscription_reference_id = m.subscription_id AND r.review_date = m.order_date
    """)
    # one visible review per order / meal: keep the newest, hide (not delete) the rest
    for column in ("order_reference_id", "subscription_order_reference_id"):
        op.execute(f"""
            UPDATE provider.reviews r
               SET is_visible = FALSE
              FROM (
                SELECT review_id, row_number() OVER (
                           PARTITION BY user_reference_id, {column} ORDER BY created_at DESC, review_id
                       ) AS rn
                  FROM provider.reviews
                 WHERE {column} IS NOT NULL AND is_visible
              ) d
             WHERE r.review_id = d.review_id AND d.rn > 1
        """)

    op.drop_index("idx_reviews_unique_daily", table_name="reviews", schema="provider")
    op.create_index(
        "uq_reviews_extra_order", "reviews", ["user_reference_id", "order_reference_id"], unique=True,
        schema="provider", postgresql_where=sa.text("order_reference_id IS NOT NULL AND is_visible"),
    )
    op.create_index(
        "uq_reviews_subscription_meal", "reviews", ["user_reference_id", "subscription_order_reference_id"], unique=True,
        schema="provider", postgresql_where=sa.text("subscription_order_reference_id IS NOT NULL AND is_visible"),
    )
    # package listings aggregate ratings per (package, kitchen)
    op.create_index(
        "idx_reviews_package_rating", "reviews", ["package_reference_id", "vendor_reference_id"], schema="provider",
        postgresql_where=sa.text("is_visible AND package_rating IS NOT NULL"),
    )


def _plans() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE master.subscription_plans SET discount_percent = 5.00, updated_at = now() "
            "WHERE lower(subscription_type) IN :types"
        ).bindparams(sa.bindparam("types", expanding=True)),
        {"types": list(FIVE_PERCENT_TYPES)},
    )

    rows = conn.execute(sa.text(
        "SELECT subscription_type, meal_slot, duration_days, free_skips, discount_percent, is_active, created_at "
        "FROM master.subscription_plans"
    )).mappings().all()
    by_type: dict = {}
    for r in rows:
        by_type.setdefault(r["subscription_type"], []).append(r)

    insert = sa.text(
        "INSERT INTO master.subscription_plans "
        "(subscription_plan_id, subscription_type, meal_slot, duration_days, free_skips, discount_percent, "
        " is_active, created_at, updated_at) "
        "VALUES (gen_random_uuid(), :t, :s, :d, :f, :p, :a, now(), now()) "
        "ON CONFLICT (subscription_type, meal_slot) DO NOTHING"
    )
    for sub_type, plans in by_type.items():
        have = {SLOT_ALIASES.get((p["meal_slot"] or "").lower(), (p["meal_slot"] or "").lower()) for p in plans}
        # the type's terms: an active single-meal plan first, else its oldest plan
        template = sorted(
            plans,
            key=lambda p: (not p["is_active"], p["meal_slot"] not in ("breakfast", "lunch", "dinner"), p["created_at"]),
        )[0]
        for slot in PLAN_SLOTS:
            if slot in have:
                continue
            conn.execute(insert, {
                "t": sub_type, "s": slot, "d": template["duration_days"], "f": template["free_skips"] or 0,
                "p": template["discount_percent"] or 0, "a": bool(template["is_active"]),
            })


def upgrade() -> None:
    _vendor_assignments()
    _package_reviews()

    op.add_column(
        "provider_notifications", sa.Column("dedupe_key", sa.String(160), nullable=True), schema="provider",
    )
    op.create_index(
        "uq_provider_notifications_dedupe", "provider_notifications", ["dedupe_key"], unique=True,
        schema="provider", postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )

    _plans()


def downgrade() -> None:
    op.drop_index("uq_provider_notifications_dedupe", table_name="provider_notifications", schema="provider")
    op.drop_column("provider_notifications", "dedupe_key", schema="provider")

    op.drop_index("idx_reviews_package_rating", table_name="reviews", schema="provider")
    op.drop_index("uq_reviews_subscription_meal", table_name="reviews", schema="provider")
    op.drop_index("uq_reviews_extra_order", table_name="reviews", schema="provider")
    # the old rule allowed one review per kitchen per day: hide newer same-day reviews first
    op.execute("""
        UPDATE provider.reviews r
           SET is_visible = FALSE
          FROM (
            SELECT review_id, row_number() OVER (
                       PARTITION BY user_reference_id, vendor_reference_id, review_date ORDER BY created_at, review_id
                   ) AS rn
              FROM provider.reviews
          ) d
         WHERE r.review_id = d.review_id AND d.rn > 1
    """)
    op.execute("""
        DELETE FROM provider.reviews r
         USING (
            SELECT review_id, row_number() OVER (
                       PARTITION BY user_reference_id, vendor_reference_id, review_date ORDER BY created_at, review_id
                   ) AS rn
              FROM provider.reviews
         ) d
         WHERE r.review_id = d.review_id AND d.rn > 1 AND NOT r.is_visible
           AND EXISTS (SELECT 1 FROM provider.reviews k WHERE k.review_id <> r.review_id
                        AND k.user_reference_id = r.user_reference_id AND k.vendor_reference_id = r.vendor_reference_id AND k.review_date = r.review_date)
    """)
    op.create_index(
        "idx_reviews_unique_daily", "reviews", ["user_reference_id", "vendor_reference_id", "review_date"], unique=True,
        schema="provider",
    )

    # back to one kitchen per partner: the earliest active assignment
    op.execute("""
        UPDATE delivery.delivery_boys b
           SET assigned_provider_reference_id = a.provider_reference_id
          FROM (
            SELECT DISTINCT ON (delivery_boy_reference_id) delivery_boy_reference_id, provider_reference_id
              FROM delivery.delivery_partner_vendors
             WHERE status = 'active'
             ORDER BY delivery_boy_reference_id, assigned_at
          ) a
         WHERE b.delivery_boy_id = a.delivery_boy_reference_id
    """)
    op.drop_table("delivery_partner_vendors", schema="delivery")
