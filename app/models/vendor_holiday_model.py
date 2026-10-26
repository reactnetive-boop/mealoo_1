import uuid

from sqlalchemy import (
    Column, String, Text, Date, DateTime, Integer, SmallInteger, Numeric, ForeignKey,
    CheckConstraint, Index, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class VendorHoliday(Base):
    """
    One holiday declaration of a kitchen (see app/domain/holidays.py).

    casual:    planned closures, as a rule: weekly (weekdays), dates (specific
               dates), range (start_date..end_date) or monthly (days of the
               month). end_date NULL = open-ended weekly / monthly rule.
    emergency: the kitchen cannot cook on one date (start_date); its meals of
               that day go to a replacement kitchen or are compensated
               (app/domain/emergency_holiday.py).

    Rows are never deleted. Removing a rule sets status 'removed', or cuts
    end_date to the removal day when part of the rule is already history.
    """

    __tablename__ = "vendor_holidays"

    __table_args__ = (
        CheckConstraint("holiday_type IN ('casual', 'emergency')", name="chk_vendor_holiday_type"),
        CheckConstraint("rule_type IN ('weekly', 'dates', 'range', 'monthly')", name="chk_vendor_holiday_rule"),
        CheckConstraint("status IN ('active', 'removed')", name="chk_vendor_holiday_status"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="chk_vendor_holiday_dates"),
        Index("idx_vendor_holidays_provider_dates", "provider_reference_id", "start_date", "end_date"),
        Index("idx_vendor_holidays_type_date", "holiday_type", "start_date"),
        Index(
            "uq_vendor_holidays_emergency_day", "provider_reference_id", "start_date", unique=True,
            postgresql_where=text("holiday_type = 'emergency' AND status = 'active'"),
        ),
        {"schema": "provider"},
    )

    vendor_holiday_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="vendor_holidays_provider_id_fkey"),
        nullable=False,
    )

    # casual | emergency
    holiday_type = Column(String(20), nullable=False)

    # weekly | dates | range | monthly
    rule_type = Column(String(20), nullable=False)

    # ISO weekdays, 1 = Monday .. 7 = Sunday (weekly rules)
    weekdays = Column(ARRAY(SmallInteger), nullable=True)

    # 1..31 (monthly rules); a day a month does not have is simply skipped
    month_days = Column(ARRAY(SmallInteger), nullable=True)

    # specific dates (dates rules, and the single date of an emergency)
    dates = Column(ARRAY(Date), nullable=True)

    # first day the rule applies (range start; the emergency date)
    start_date = Column(Date, nullable=False)

    # last day the rule applies, inclusive; NULL = no end
    end_date = Column(Date, nullable=True)

    reason = Column(Text, nullable=True)

    # active | removed
    status = Column(String(20), nullable=False, default="active")

    # emergency: pending | processing | completed | completed_with_errors
    # casual: completed once existing subscriptions were re-planned
    processing_status = Column(String(30), nullable=False, default="not_required")

    affected_meals = Column(Integer, nullable=False, default=0)
    replaced_meals = Column(Integer, nullable=False, default=0)
    compensated_meals = Column(Integer, nullable=False, default=0)
    failed_meals = Column(Integer, nullable=False, default=0)
    affected_subscriptions = Column(Integer, nullable=False, default=0)

    # provider | admin | migration
    created_by_type = Column(String(20), nullable=False, default="provider")
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    removed_by = Column(UUID(as_uuid=True), nullable=True)
    removed_at = Column(DateTime(timezone=True), nullable=True)
    removed_reason = Column(Text, nullable=True)

    # an edit of a rule that had already started: the earlier version
    replaces_holiday_id = Column(UUID(as_uuid=True), nullable=True)

    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VendorHolidayMeal(Base):
    """
    One meal an emergency holiday affected and what happened to it. Unique per
    (holiday, meal), so a meal is processed exactly once per holiday; the
    money and skip movements carry their own idempotency keys as well.
    """

    __tablename__ = "vendor_holiday_meals"

    __table_args__ = (
        UniqueConstraint("vendor_holiday_reference_id", "order_reference_id", name="uq_vendor_holiday_meal"),
        CheckConstraint(
            "outcome IN ('pending', 'replaced', 'compensated', 'not_affected', 'failed')",
            name="chk_vendor_holiday_meal_outcome",
        ),
        Index("idx_vendor_holiday_meals_order", "order_reference_id"),
        Index("idx_vendor_holiday_meals_status", "processing_status", "notification_status"),
        {"schema": "provider"},
    )

    vendor_holiday_meal_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    vendor_holiday_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.vendor_holidays.vendor_holiday_id", name="vendor_holiday_meals_holiday_id_fkey"),
        nullable=False,
    )
    order_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.orders.order_id", name="vendor_holiday_meals_order_id_fkey"),
        nullable=False,
    )
    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="vendor_holiday_meals_subscription_id_fkey"),
        nullable=False,
    )
    user_reference_id = Column(
        UUID(as_uuid=True), ForeignKey("auth.users.user_id", name="vendor_holiday_meals_user_id_fkey"), nullable=False,
    )
    original_vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="vendor_holiday_meals_vendor_id_fkey"),
        nullable=False,
    )
    meal_date = Column(Date, nullable=False)
    meal_slot = Column(String(20), nullable=False)

    # pending | replaced | compensated | not_affected (delivered / skipped /
    # refunded before it was processed) | failed
    outcome = Column(String(30), nullable=False, default="pending")

    replacement_vendor_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="vendor_holiday_meals_replacement_vendor_id_fkey"),
        nullable=True,
    )
    replacement_package_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master.menu_packages.package_id", name="vendor_holiday_meals_replacement_package_id_fkey"),
        nullable=True,
    )
    # per-meal prices compared for the replacement (unit price x quantity)
    original_meal_price = Column(Numeric(10, 2), nullable=True)
    replacement_meal_price = Column(Numeric(10, 2), nullable=True)
    # the meal's value credited to the wallet (no replacement)
    meal_amount = Column(Numeric(10, 2), nullable=True)

    wallet_transaction_reference_id = Column(UUID(as_uuid=True), nullable=True)
    skip_credit_reference_id = Column(UUID(as_uuid=True), nullable=True)

    # pending | completed | failed
    processing_status = Column(String(20), nullable=False, default="pending")
    # not_required | pending | completed | failed
    compensation_status = Column(String(20), nullable=False, default="not_required")
    # pending | sent | failed | not_required
    notification_status = Column(String(20), nullable=False, default="pending")

    attempts = Column(SmallInteger, nullable=False, default=0)
    notification_attempts = Column(SmallInteger, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    notified_at = Column(DateTime(timezone=True), nullable=True)


class VendorHolidayRequest(Base):
    """
    A kitchen's request to change its holidays, waiting for an admin.

    Nothing a kitchen asks for touches its schedule until an admin approves
    it: the approved schedule is provider.vendor_holidays only, so a pending,
    rejected, withdrawn or expired request never closes (or opens) a day.

    request_type  emergency  one date (holiday_date), optional reason
                  regular    weekly days (weekdays from start_date on)
    action        add | update (target_holiday_id) | remove (target_holiday_id)

    dedupe_key is unique among the pending requests of a kitchen
    ("emergency:2026-10-06", "regular:add:6,7", "regular:target:<id>"), so
    sending the same request twice gives back the one already waiting.
    """

    __tablename__ = "vendor_holiday_requests"

    __table_args__ = (
        CheckConstraint("request_type IN ('emergency', 'regular')", name="chk_holiday_request_type"),
        CheckConstraint("action IN ('add', 'update', 'remove')", name="chk_holiday_request_action"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'withdrawn', 'expired')", name="chk_holiday_request_status",
        ),
        Index("idx_holiday_requests_provider", "provider_reference_id", "created_at"),
        Index("idx_holiday_requests_status", "status", "created_at"),
        Index(
            "uq_holiday_requests_pending", "provider_reference_id", "dedupe_key", unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        {"schema": "provider"},
    )

    request_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.providers.provider_id", name="vendor_holiday_requests_provider_id_fkey"),
        nullable=False,
    )

    # emergency | regular
    request_type = Column(String(20), nullable=False)

    # add | update | remove
    action = Column(String(20), nullable=False, default="add")

    # the approved holiday an update / remove changes
    target_holiday_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.vendor_holidays.vendor_holiday_id", name="vendor_holiday_requests_target_fkey"),
        nullable=True,
    )

    # emergency: the date the kitchen cannot cook
    holiday_date = Column(Date, nullable=True)

    # regular: ISO weekdays (1 = Monday .. 7 = Sunday) and the first day they apply
    weekdays = Column(ARRAY(SmallInteger), nullable=True)
    start_date = Column(Date, nullable=True)

    reason = Column(Text, nullable=True)

    # pending | approved | rejected | withdrawn | expired
    status = Column(String(20), nullable=False, default="pending")

    dedupe_key = Column(String(120), nullable=False)

    # what the request would change when it was sent (shown to the admin)
    impact = Column(JSONB, nullable=True)

    decided_by = Column(UUID(as_uuid=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(Text, nullable=True)

    # the approved holiday created (or changed) by this request
    resulting_holiday_id = Column(UUID(as_uuid=True), nullable=True)
    # what applying it did (re-planned subscriptions, refunds, skips, ...)
    result = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class VendorHolidaySubscription(Base):
    """
    One active subscription of a kitchen on an approved emergency holiday:
    its extra free skip (exactly one per holiday) and the notice telling the
    customer about the closure, the refunded meals, the wallet balance and the
    skip. Unique per (holiday, subscription), so retries never credit twice.
    """

    __tablename__ = "vendor_holiday_subscriptions"

    __table_args__ = (
        UniqueConstraint("vendor_holiday_reference_id", "subscription_reference_id",
                         name="uq_vendor_holiday_subscription"),
        CheckConstraint("skip_status IN ('pending', 'completed', 'failed')", name="chk_vh_sub_skip_status"),
        Index("idx_vendor_holiday_subscriptions_status", "skip_status"),
        {"schema": "provider"},
    )

    vendor_holiday_subscription_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    vendor_holiday_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("provider.vendor_holidays.vendor_holiday_id", name="vendor_holiday_subscriptions_holiday_fkey"),
        nullable=False,
    )
    subscription_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription.subscriptions.subscription_id", name="vendor_holiday_subscriptions_sub_fkey"),
        nullable=False,
    )
    user_reference_id = Column(
        UUID(as_uuid=True), ForeignKey("auth.users.user_id", name="vendor_holiday_subscriptions_user_fkey"),
        nullable=False,
    )

    skip_credit_reference_id = Column(UUID(as_uuid=True), nullable=True)
    # pending | completed | failed
    skip_status = Column(String(20), nullable=False, default="pending")
    attempts = Column(SmallInteger, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    # meals of this subscription refunded for the holiday, and their total
    refunded_meals = Column(Integer, nullable=False, default=0)
    refund_amount = Column(Numeric(10, 2), nullable=False, default=0)

    notice_queued_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HolidayNotice(Base):
    """
    Notification log of everything sent about kitchen holidays: to admins
    (new request), kitchens (decision), customers (closure, refund, skip,
    schedule change) and delivery partners (no pickup, schedule change).

    A notice is written in the same transaction as the business change it
    reports (so it is never sent for something that did not commit), then
    delivered on its own. A failed delivery is retried later from this row
    alone - refunds, skips and schedule changes are never run again.
    dedupe_key is unique: one notice per event and recipient.
    """

    __tablename__ = "holiday_notices"

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_holiday_notices_dedupe"),
        CheckConstraint("audience IN ('admin', 'provider', 'customer', 'delivery_boy')",
                        name="chk_holiday_notice_audience"),
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="chk_holiday_notice_status"),
        Index("idx_holiday_notices_status", "status", "created_at"),
        Index("idx_holiday_notices_holiday", "vendor_holiday_reference_id"),
        Index("idx_holiday_notices_request", "request_reference_id"),
        {"schema": "provider"},
    )

    holiday_notice_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    request_reference_id = Column(UUID(as_uuid=True), nullable=True)
    vendor_holiday_reference_id = Column(UUID(as_uuid=True), nullable=True)

    # admin | provider | customer | delivery_boy
    audience = Column(String(20), nullable=False)
    # the user / kitchen / partner; NULL for admins (every admin sees it)
    recipient_id = Column(UUID(as_uuid=True), nullable=True)

    type = Column(String(50), nullable=False)
    title = Column(String(150), nullable=False)
    body = Column(Text, nullable=False)
    data = Column(JSONB, nullable=True)

    dedupe_key = Column(String(160), nullable=False)

    # pending | sent | failed
    status = Column(String(20), nullable=False, default="pending")
    attempts = Column(SmallInteger, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
