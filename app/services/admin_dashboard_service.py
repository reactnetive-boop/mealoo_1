"""
Admin dashboard: today's operations, money and 14-day trends.

Each table is read once with conditional aggregates (one query per table, not
one per number) and the result is cached for CACHE_SECONDS per process, so a
panel that refreshes often does not hammer the database. `refresh=True`
bypasses the cache.
"""

import threading
import time
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import Date, and_, case, cast, func
from sqlalchemy.orm import Session

from app.core.clock import BUSINESS_TZ, today_local
from app.domain.slots import SLOT_WINDOWS
from app.domain.status import SUB_OPEN_STATUSES, SUB_UNPICKED_STATUSES
from app.models.complaint_model import Complaint
from app.models.delivery_boy_complaint_model import DeliveryBoyComplaint
from app.models.delivery_boy_model import DeliveryBoy
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.payout_request_model import PayoutRequest
from app.models.platform_ledger_model import PlatformLedgerEntry
from app.models.provider_complaint_model import ProviderComplaint
from app.models.provider_model import Provider
from app.models.provider_wallet_model import ProviderWallet
from app.models.subscription_model import Subscription
from app.models.user_model import User
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction

CACHE_SECONDS = 60
TREND_DAYS = 14
# money customers paid for food (wallet debits) and what they got back
_SPEND_REASONS = ("subscription_payment", "order_placed")
_REFUND_REASONS = ("order_cancel_refund", "subscription_cancel_refund", "free_skip_refund", "order_rejected_refund")

_cache: dict = {}
_lock = threading.Lock()


def _n(condition):
    return func.count(case((condition, 1)))


def _money(value) -> str:
    return str(value if value is not None else Decimal("0"))


def _local_day(column):
    return cast(func.timezone(str(BUSINESS_TZ), column), Date)


def _on_time_case(model, day_col):
    """1 when delivered before the end of the slot's delivery window."""
    whens = []
    for slot, (_, end) in SLOT_WINDOWS.items():
        whens.append((
            and_(model.meal_slot == slot,
                 func.timezone(str(BUSINESS_TZ), model.delivered_at) <= func.cast(day_col, Date) + end),
            1,
        ))
    return func.count(case(*whens))


def _trends(db: Session, today) -> dict:
    start = today - timedelta(days=TREND_DAYS - 1)
    days = [start + timedelta(days=i) for i in range(TREND_DAYS)]

    spend = dict(
        db.query(_local_day(WalletTransaction.created_at), func.sum(WalletTransaction.amount))
        .filter(WalletTransaction.type == "debit", WalletTransaction.reason.in_(_SPEND_REASONS),
                _local_day(WalletTransaction.created_at) >= start)
        .group_by(_local_day(WalletTransaction.created_at)).all()
    )
    refunds = dict(
        db.query(_local_day(WalletTransaction.created_at), func.sum(WalletTransaction.amount))
        .filter(WalletTransaction.type == "credit", WalletTransaction.reason.in_(_REFUND_REASONS),
                _local_day(WalletTransaction.created_at) >= start)
        .group_by(_local_day(WalletTransaction.created_at)).all()
    )
    new_customers = dict(
        db.query(_local_day(User.created_at), func.count())
        .filter(_local_day(User.created_at) >= start)
        .group_by(_local_day(User.created_at)).all()
    )

    delivered: dict = {}
    on_time: dict = {}
    failed: dict = {}
    for model, day_col in ((Order, Order.order_date), (ExtraOrder, ExtraOrder.delivery_date)):
        rows = (
            db.query(day_col, _n(model.status == "delivered"), _on_time_case(model, day_col),
                     _n(model.status == "delivery_failed"))
            .filter(day_col >= start, day_col <= today)
            .group_by(day_col).all()
        )
        for day, n_delivered, n_on_time, n_failed in rows:
            delivered[day] = delivered.get(day, 0) + n_delivered
            on_time[day] = on_time.get(day, 0) + n_on_time
            failed[day] = failed.get(day, 0) + n_failed

    series = []
    for day in days:
        gross = spend.get(day) or Decimal("0")
        back = refunds.get(day) or Decimal("0")
        n = delivered.get(day, 0)
        series.append({
            "date": day,
            "gmv": _money(gross),
            "refunds": _money(back),
            "net_sales": _money(gross - back),
            "meals_delivered": n,
            "delivery_failed": failed.get(day, 0),
            "on_time_rate": round(on_time.get(day, 0) / n, 3) if n else None,
            "new_customers": new_customers.get(day, 0),
        })
    total_delivered = sum(delivered.values())
    return {
        "days": series,
        "gmv_total": _money(sum((Decimal(d["gmv"]) for d in series), Decimal("0"))),
        "on_time_rate": round(sum(on_time.values()) / total_delivered, 3) if total_delivered else None,
    }


def _compute(db: Session) -> dict:
    today = today_local()

    users = db.query(func.count(User.id), _n(User.status == "active")).one()
    repeat_customers = (
        db.query(func.count())
        .select_from(
            db.query(Subscription.user_reference_id)
            .group_by(Subscription.user_reference_id)
            .having(func.count() > 1)
            .subquery()
        ).scalar()
    )
    providers = db.query(
        func.count(Provider.id),
        _n(Provider.is_profile_completed == True),  # noqa: E712
        _n(and_(Provider.approval_status == "pending", Provider.is_profile_completed == True)),  # noqa: E712
        _n(and_(Provider.approval_status == "approved", Provider.is_active == True)),  # noqa: E712
    ).one()
    partners = db.query(
        func.count(DeliveryBoy.id),
        _n(DeliveryBoy.is_active == True),  # noqa: E712
        _n(and_(DeliveryBoy.is_online == True, DeliveryBoy.approval_status == "approved")),  # noqa: E712
        _n(DeliveryBoy.approval_status == "pending"),
    ).one()
    packages = db.query(
        _n(and_(MenuPackage.approval_status == "pending", MenuPackage.deleted_at.is_(None))),
        _n(MenuPackage.pending_changes.isnot(None)),
    ).one()
    subs = db.query(
        func.count(Subscription.subscription_id),
        _n(Subscription.status == "active"),
        _n(Subscription.status == "paused"),
    ).one()
    meals_today = db.query(
        func.count(Order.order_id),
        _n(Order.status == "delivered"),
        _n(Order.status.in_(SUB_OPEN_STATUSES)),
        _n(and_(Order.status.in_(SUB_UNPICKED_STATUSES), Order.delivery_boy_reference_id.is_(None))),
        _n(Order.status == "delivery_failed"),
    ).filter(Order.order_date == today).one()
    extras = db.query(
        _n(ExtraOrder.delivery_date == today),
        _n(ExtraOrder.status == "pending"),
    ).one()
    complaints = [
        db.query(func.count()).select_from(model).filter(model.status == "open").scalar()
        for model in (Complaint, ProviderComplaint, DeliveryBoyComplaint)
    ]
    kitchen_money = db.query(
        func.sum(ProviderWallet.total_earned), func.sum(ProviderWallet.total_withdrawn), func.sum(ProviderWallet.balance)
    ).one()
    partner_balance = db.query(func.sum(DeliveryBoyWallet.balance)).scalar()
    customer_balance = db.query(func.sum(Wallet.balance)).scalar()
    signed = case(
        (PlatformLedgerEntry.direction == "credit", PlatformLedgerEntry.amount), else_=-PlatformLedgerEntry.amount
    )
    platform_net = db.query(func.coalesce(func.sum(signed), 0)).scalar()
    platform_by_type = {
        f"{entry_type}:{direction}": str(amount)
        for entry_type, direction, amount in db.query(
            PlatformLedgerEntry.entry_type, PlatformLedgerEntry.direction, func.sum(PlatformLedgerEntry.amount)
        ).group_by(PlatformLedgerEntry.entry_type, PlatformLedgerEntry.direction)
    }
    payouts = db.query(func.count(), func.sum(PayoutRequest.amount)).filter(PayoutRequest.status == "pending").one()

    return {
        "success": True,
        "business_date": today,
        "users": {"total": users[0], "active": users[1], "inactive": users[0] - users[1],
                  "repeat_subscribers": repeat_customers},
        "providers": {
            "total": providers[0],
            "profile_completed": providers[1],
            "incomplete": providers[0] - providers[1],
            "pending_approval": providers[2],
            "approved_active": providers[3],
        },
        "delivery_boys": {
            "total": partners[0],
            "active": partners[1],
            "inactive": partners[0] - partners[1],
            "online": partners[2],
            "pending_approval": partners[3],
        },
        "packages": {"pending_approval": packages[0], "pending_changes": packages[1]},
        "subscriptions": {"total": subs[0], "active": subs[1], "paused": subs[2]},
        "orders": {
            "today_total": meals_today[0],
            "today_delivered": meals_today[1],
            "today_pending": meals_today[2],
            "today_unassigned": meals_today[3],
            "today_delivery_failed": meals_today[4],
            "extra_orders_today": extras[0],
            "extra_orders_awaiting_kitchen": extras[1],
        },
        "complaints": {
            "open_user_complaints": complaints[0],
            "open_provider_complaints": complaints[1],
            "open_delivery_complaints": complaints[2],
            "total_open": sum(complaints),
        },
        "revenue": {
            # money is returned as strings to avoid float rounding
            "total_earned_by_providers": _money(kitchen_money[0]),
            "total_withdrawn_by_providers": _money(kitchen_money[1]),
            "provider_wallet_balance": _money(kitchen_money[2]),
            "delivery_partner_wallet_balance": _money(partner_balance),
            "user_wallet_total_balance": _money(customer_balance),
            "platform_net": str(platform_net),
            "platform_by_type": platform_by_type,
            "pending_withdrawals": payouts[0],
            "pending_withdrawal_amount": _money(payouts[1]),
        },
        "trends": _trends(db, today),
    }


class AdminDashboardService:

    @staticmethod
    def get_stats(db: Session, refresh: bool = False):
        key = today_local()
        now = time.monotonic()
        with _lock:
            hit = _cache.get(key)
            if hit and not refresh and now - hit[0] < CACHE_SECONDS:
                return {**hit[1], "cached": True}
        stats = _compute(db)
        with _lock:
            _cache.clear()
            _cache[key] = (now, stats)
        return {**stats, "cached": False}
