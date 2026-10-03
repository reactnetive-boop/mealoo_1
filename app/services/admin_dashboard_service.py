from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.models.user_model import User
from app.models.provider_model import Provider
from app.models.delivery_boy_model import DeliveryBoy
from app.models.subscription_model import Subscription
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder
from app.models.complaint_model import Complaint
from app.models.provider_complaint_model import ProviderComplaint
from app.models.delivery_boy_complaint_model import DeliveryBoyComplaint
from app.models.menu_package_model import MenuPackage
from app.models.wallet_model import Wallet
from app.models.provider_wallet_model import ProviderWallet
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.platform_ledger_model import PlatformLedgerEntry
from app.models.payout_request_model import PayoutRequest


def _count(db, column, *filters) -> int:
    return db.query(func.count(column)).filter(*filters).scalar() or 0


def _sum(db, column, *filters):
    return db.query(func.coalesce(func.sum(column), 0)).filter(*filters).scalar()


class AdminDashboardService:

    @staticmethod
    def get_stats(db: Session):
        today = today_local()

        total_users = _count(db, User.id)
        active_users = _count(db, User.id, User.status == "active")

        total_providers = _count(db, Provider.id)
        completed_providers = _count(db, Provider.id, Provider.is_profile_completed == True)  # noqa: E712
        pending_providers = _count(
            db, Provider.id, Provider.approval_status == "pending", Provider.is_profile_completed == True  # noqa: E712
        )
        approved_providers = _count(db, Provider.id, Provider.approval_status == "approved", Provider.is_active == True)  # noqa: E712

        total_dboys = _count(db, DeliveryBoy.id)
        active_dboys = _count(db, DeliveryBoy.id, DeliveryBoy.is_active == True)  # noqa: E712
        online_dboys = _count(
            db, DeliveryBoy.id, DeliveryBoy.is_online == True, DeliveryBoy.approval_status == "approved"  # noqa: E712
        )
        pending_dboys = _count(db, DeliveryBoy.id, DeliveryBoy.approval_status == "pending")

        pending_packages = _count(
            db, MenuPackage.package_id, MenuPackage.approval_status == "pending", MenuPackage.deleted_at.is_(None)
        )

        total_subs = _count(db, Subscription.subscription_id)
        active_subs = _count(db, Subscription.subscription_id, Subscription.status == "active")
        paused_subs = _count(db, Subscription.subscription_id, Subscription.status == "paused")

        todays_orders = _count(db, Order.order_id, Order.order_date == today)
        delivered_today = _count(db, Order.order_id, Order.order_date == today, Order.status == "delivered")
        pending_today = _count(
            db, Order.order_id, Order.order_date == today,
            Order.status.in_(["scheduled", "preparing", "out_for_delivery"]),
        )
        unassigned_today = _count(
            db, Order.order_id, Order.order_date == today,
            Order.status.in_(["scheduled", "preparing"]), Order.delivery_boy_reference_id.is_(None),
        )
        extra_today = _count(db, ExtraOrder.extra_order_id, ExtraOrder.delivery_date == today)
        extra_pending = _count(db, ExtraOrder.extra_order_id, ExtraOrder.status == "pending")

        open_user_complaints = _count(db, Complaint.complaint_id, Complaint.status == "open")
        open_provider_complaints = _count(db, ProviderComplaint.provider_complaint_id, ProviderComplaint.status == "open")
        open_delivery_complaints = _count(
            db, DeliveryBoyComplaint.delivery_boy_complaint_id, DeliveryBoyComplaint.status == "open"
        )

        total_earned = _sum(db, ProviderWallet.total_earned)
        total_withdrawn = _sum(db, ProviderWallet.total_withdrawn)
        provider_balance = _sum(db, ProviderWallet.balance)
        partner_balance = _sum(db, DeliveryBoyWallet.balance)
        user_wallet_total = _sum(db, Wallet.balance)

        signed = case(
            (PlatformLedgerEntry.direction == "credit", PlatformLedgerEntry.amount),
            else_=-PlatformLedgerEntry.amount,
        )
        platform_net = db.query(func.coalesce(func.sum(signed), 0)).scalar()
        platform_by_type = {
            f"{entry_type}:{direction}": str(amount)
            for entry_type, direction, amount in db.query(
                PlatformLedgerEntry.entry_type, PlatformLedgerEntry.direction, func.sum(PlatformLedgerEntry.amount)
            ).group_by(PlatformLedgerEntry.entry_type, PlatformLedgerEntry.direction)
        }
        pending_payouts = _count(db, PayoutRequest.payout_request_id, PayoutRequest.status == "pending")
        pending_payout_amount = _sum(db, PayoutRequest.amount, PayoutRequest.status == "pending")

        return {
            "success": True,
            "business_date": today,
            "users": {"total": total_users, "active": active_users, "inactive": total_users - active_users},
            "providers": {
                "total": total_providers,
                "profile_completed": completed_providers,
                "incomplete": total_providers - completed_providers,
                "pending_approval": pending_providers,
                "approved_active": approved_providers,
            },
            "delivery_boys": {
                "total": total_dboys,
                "active": active_dboys,
                "inactive": total_dboys - active_dboys,
                "online": online_dboys,
                "pending_approval": pending_dboys,
            },
            "packages": {"pending_approval": pending_packages},
            "subscriptions": {"total": total_subs, "active": active_subs, "paused": paused_subs},
            "orders": {
                "today_total": todays_orders,
                "today_delivered": delivered_today,
                "today_pending": pending_today,
                "today_unassigned": unassigned_today,
                "extra_orders_today": extra_today,
                "extra_orders_awaiting_kitchen": extra_pending,
            },
            "complaints": {
                "open_user_complaints": open_user_complaints,
                "open_provider_complaints": open_provider_complaints,
                "open_delivery_complaints": open_delivery_complaints,
                "total_open": open_user_complaints + open_provider_complaints + open_delivery_complaints,
            },
            "revenue": {
                # money is returned as strings to avoid float rounding
                "total_earned_by_providers": str(total_earned),
                "total_withdrawn_by_providers": str(total_withdrawn),
                "provider_wallet_balance": str(provider_balance),
                "delivery_partner_wallet_balance": str(partner_balance),
                "user_wallet_total_balance": str(user_wallet_total),
                "platform_net": str(platform_net),
                "platform_by_type": platform_by_type,
                "pending_withdrawals": pending_payouts,
                "pending_withdrawal_amount": str(pending_payout_amount),
            },
        }
