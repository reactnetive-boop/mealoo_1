from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.delivery_boy_repository import DeliveryBoyRepository
from app.repositories.delivery_boy_repository import DeliveryBoyRepository as Repo
from app.repositories.provider_wallet_repository import ProviderWalletRepository
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage


class DeliveryBoyOrderService:

    # ── Profile ───────────────────────────────────────────

    @staticmethod
    def get_profile(db: Session, delivery_boy_id: str):
        boy = Repo.get_by_id(db, delivery_boy_id)
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")
        return {"success": True, "profile": boy}

    @staticmethod
    def update_profile(db: Session, delivery_boy_id: str, payload):
        boy = Repo.get_by_id(db, delivery_boy_id)
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")

        update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
        boy = Repo.update(db, boy, update_data)
        return {"success": True, "message": "Profile updated", "profile": boy}

    # ── Subscription Orders ───────────────────────────────

    @staticmethod
    def list_orders(
        db: Session,
        delivery_boy_id: str,
        order_date: date = None,
        meal_slot: str = None,
        status: str = None
    ):
        if order_date is None:
            order_date = date.today()

        orders = Repo.get_subscription_orders(
            db, delivery_boy_id,
            order_date=order_date,
            meal_slot=meal_slot,
            status=status
        )
        return {"success": True, "total": len(orders), "orders": orders}

    @staticmethod
    def get_order_detail(db: Session, delivery_boy_id: str, order_id: str):
        row = Repo.get_subscription_order_detail(db, order_id, delivery_boy_id)
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")

        order, user, address, subscription = row

        sp_rows = Repo.get_subscription_packages_for_order(db, subscription.id)
        packages = [
            {
                "package_id": mp.package_id,
                "package_name": mp.package_name,
                "quantity": sp.quantity
            }
            for sp, mp in sp_rows
        ]

        return {
            "success": True,
            "order": order,
            "user": user,
            "delivery_address": address,
            "packages": packages
        }

    @staticmethod
    def pickup_order(db: Session, delivery_boy_id: str, order_id: str, payload):
        order = Repo.get_subscription_order_by_id(db, order_id, delivery_boy_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status not in ("scheduled", "preparing"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot pick up order in '{order.status}' status"
            )

        order.status = "out_for_delivery"
        if payload.delivery_notes:
            order.delivery_notes = payload.delivery_notes

        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "message": "Order picked up — marked as out for delivery",
            "order_id": order.id,
            "status": order.status
        }

    @staticmethod
    def deliver_order(db: Session, delivery_boy_id: str, order_id: str, payload):
        order = Repo.get_subscription_order_by_id(db, order_id, delivery_boy_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status != "out_for_delivery":
            raise HTTPException(
                status_code=400,
                detail=f"Order must be 'out_for_delivery' before marking delivered. Current: '{order.status}'"
            )

        if order.otp_for_delivery and order.otp_for_delivery != payload.otp:
            raise HTTPException(status_code=400, detail="Invalid delivery OTP")

        order.status = "delivered"
        order.delivered_at = datetime.now(timezone.utc)
        if payload.delivery_notes:
            order.delivery_notes = payload.delivery_notes

        # Credit provider wallet for this delivery
        sub_packages = (
            db.query(SubscriptionPackage)
            .filter(SubscriptionPackage.subscription_id == order.subscription_id)
            .all()
        )
        order_amount = sum(
            Decimal(str(sp.unit_price)) * sp.quantity for sp in sub_packages
        )
        if order_amount > 0:
            wallet = ProviderWalletRepository.get_or_create(db, order.vendor_id)
            balance_before = Decimal(str(wallet.balance))
            ProviderWalletRepository.credit(db, wallet, order_amount)
            ProviderWalletRepository.create_transaction(db, {
                "wallet_id": wallet.id,
                "provider_id": order.vendor_id,
                "type": "credit",
                "reason": "order_delivered",
                "amount": order_amount,
                "balance_before": balance_before,
                "balance_after": Decimal(str(wallet.balance)),
                "reference_id": order.id,
                "reference_type": "order",
                "description": f"Delivery confirmed for {order.order_date} ({order.meal_slot})",
            })

        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "message": "Order delivered successfully",
            "order_id": order.id,
            "status": order.status
        }

    # ── Extra Orders ──────────────────────────────────────

    @staticmethod
    def list_extra_orders(
        db: Session,
        delivery_boy_id: str,
        delivery_date: date = None,
        meal_slot: str = None,
        status: str = None
    ):
        if delivery_date is None:
            delivery_date = date.today()

        orders = Repo.get_extra_orders(
            db, delivery_boy_id,
            delivery_date=delivery_date,
            meal_slot=meal_slot,
            status=status
        )
        return {"success": True, "total": len(orders), "orders": orders}

    @staticmethod
    def get_extra_order_detail(db: Session, delivery_boy_id: str, order_id: str):
        row = Repo.get_extra_order_detail(db, order_id, delivery_boy_id)
        if not row:
            raise HTTPException(status_code=404, detail="Extra order not found")

        order, user, address, package = row

        return {
            "success": True,
            "order": order,
            "user": user,
            "delivery_address": address,
            "package_name": package.package_name
        }

    @staticmethod
    def pickup_extra_order(db: Session, delivery_boy_id: str, order_id: str, payload):
        order = Repo.get_extra_order_by_id(db, order_id, delivery_boy_id)
        if not order:
            raise HTTPException(status_code=404, detail="Extra order not found")

        if order.status not in ("confirmed", "preparing"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot pick up extra order in '{order.status}' status"
            )

        order.status = "out_for_delivery"
        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "message": "Extra order picked up — marked as out for delivery",
            "order_id": order.id,
            "status": order.status
        }

    @staticmethod
    def deliver_extra_order(db: Session, delivery_boy_id: str, order_id: str, payload):
        order = Repo.get_extra_order_by_id(db, order_id, delivery_boy_id)
        if not order:
            raise HTTPException(status_code=404, detail="Extra order not found")

        if order.status != "out_for_delivery":
            raise HTTPException(
                status_code=400,
                detail=f"Extra order must be 'out_for_delivery'. Current: '{order.status}'"
            )

        order.status = "delivered"

        # Credit provider wallet
        order_amount = Decimal(str(order.total_price))
        if order_amount > 0:
            wallet = ProviderWalletRepository.get_or_create(db, order.vendor_id)
            balance_before = Decimal(str(wallet.balance))
            ProviderWalletRepository.credit(db, wallet, order_amount)
            ProviderWalletRepository.create_transaction(db, {
                "wallet_id": wallet.id,
                "provider_id": order.vendor_id,
                "type": "credit",
                "reason": "order_delivered",
                "amount": order_amount,
                "balance_before": balance_before,
                "balance_after": Decimal(str(wallet.balance)),
                "reference_id": order.id,
                "reference_type": "extra_order",
                "description": f"Extra order delivered on {order.delivery_date} ({order.meal_slot})",
            })

        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "message": "Extra order delivered successfully",
            "order_id": order.id,
            "status": order.status
        }
