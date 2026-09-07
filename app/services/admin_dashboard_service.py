from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user_model import User
from app.models.provider_model import Provider
from app.models.delivery_boy_model import DeliveryBoy
from app.models.subscription_model import Subscription
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder
from app.models.complaint_model import Complaint
from app.models.provider_complaint_model import ProviderComplaint
from app.models.payment_model import Payment
from app.models.wallet_model import Wallet
from app.models.provider_wallet_model import ProviderWallet


class AdminDashboardService:

    @staticmethod
    def get_stats(db: Session):
        today = date.today()

        # Users
        total_users = db.query(func.count(User.id)).scalar()
        active_users = db.query(func.count(User.id)).filter(User.status == "active").scalar()

        # Providers
        total_providers = db.query(func.count(Provider.id)).scalar()
        completed_providers = db.query(func.count(Provider.id)).filter(Provider.is_profile_completed == True).scalar()

        # Delivery boys
        total_dboys = db.query(func.count(DeliveryBoy.id)).scalar()
        active_dboys = db.query(func.count(DeliveryBoy.id)).filter(DeliveryBoy.is_active == True).scalar()

        # Subscriptions
        total_subs = db.query(func.count(Subscription.subscription_id)).scalar()
        active_subs = db.query(func.count(Subscription.subscription_id)).filter(Subscription.status == "active").scalar()

        # Orders today
        todays_orders = db.query(func.count(Order.order_id)).filter(Order.order_date == today).scalar()
        delivered_today = db.query(func.count(Order.order_id)).filter(
            Order.order_date == today, Order.status == "delivered"
        ).scalar()
        pending_today = db.query(func.count(Order.order_id)).filter(
            Order.order_date == today,
            Order.status.in_(["scheduled", "preparing", "out_for_delivery"])
        ).scalar()

        extra_today = db.query(func.count(ExtraOrder.extra_order_id)).filter(ExtraOrder.delivery_date == today).scalar()

        # Complaints
        open_user_complaints = db.query(func.count(Complaint.complaint_id)).filter(Complaint.status == "open").scalar()
        open_provider_complaints = db.query(func.count(ProviderComplaint.provider_complaint_id)).filter(
            ProviderComplaint.status == "open"
        ).scalar()

        # Revenue — sum of provider wallet total_earned across all providers
        total_earned = db.query(func.coalesce(func.sum(ProviderWallet.total_earned), 0)).scalar()
        total_withdrawn = db.query(func.coalesce(func.sum(ProviderWallet.total_withdrawn), 0)).scalar()

        # User wallet total balance
        user_wallet_total = db.query(func.coalesce(func.sum(Wallet.balance), 0)).scalar()

        return {
            "success": True,
            "users": {
                "total": total_users,
                "active": active_users,
                "inactive": total_users - active_users
            },
            "providers": {
                "total": total_providers,
                "profile_completed": completed_providers,
                "incomplete": total_providers - completed_providers
            },
            "delivery_boys": {
                "total": total_dboys,
                "active": active_dboys,
                "inactive": total_dboys - active_dboys
            },
            "subscriptions": {
                "total": total_subs,
                "active": active_subs
            },
            "orders": {
                "today_total": todays_orders,
                "today_delivered": delivered_today,
                "today_pending": pending_today,
                "extra_orders_today": extra_today
            },
            "complaints": {
                "open_user_complaints": open_user_complaints,
                "open_provider_complaints": open_provider_complaints,
                "total_open": open_user_complaints + open_provider_complaints
            },
            "revenue": {
                "total_earned_by_providers": float(total_earned),
                "total_withdrawn_by_providers": float(total_withdrawn),
                "provider_wallet_balance": float(total_earned) - float(total_withdrawn),
                "user_wallet_total_balance": float(user_wallet_total)
            }
        }
