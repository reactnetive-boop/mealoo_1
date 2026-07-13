from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import DELIVERY_BOY_FEE_PER_DELIVERY
from app.repositories.delivery_boy_repository import DeliveryBoyRepository
from app.repositories.delivery_boy_repository import DeliveryBoyRepository as Repo
from app.repositories.delivery_boy_wallet_repository import DeliveryBoyWalletRepository
from app.repositories.provider_wallet_repository import ProviderWalletRepository
from app.models.order_model import Order
from app.models.extra_order_model import ExtraOrder
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.schemas.delivery_boy_schema import DeliveryBoyProfileResponse


def _credit_delivery_boy_for_delivery(
    db: Session,
    delivery_boy_id,
    reference_id,
    reference_type: str,
    description: str,
):
    """Flat per-delivery payout + notification. Flushes only — caller commits."""
    fee = Decimal(DELIVERY_BOY_FEE_PER_DELIVERY)
    if fee <= 0:
        return

    wallet = DeliveryBoyWalletRepository.get_or_create(db, delivery_boy_id)
    balance_before = Decimal(str(wallet.balance))
    DeliveryBoyWalletRepository.credit(db, wallet, fee)
    DeliveryBoyWalletRepository.create_transaction(db, {
        "wallet_reference_id": wallet.delivery_boy_wallet_id,
        "delivery_boy_reference_id": delivery_boy_id,
        "type": "credit",
        "reason": "delivery_payout",
        "amount": fee,
        "balance_before": balance_before,
        "balance_after": Decimal(str(wallet.balance)),
        "reference_id": reference_id,
        "reference_type": reference_type,
        "description": description,
    })
    Repo.create_notification(
        db,
        delivery_boy_id,
        type="payout",
        title="Delivery payout credited",
        body=f"₹{fee} added to your wallet. {description}",
        data={"reference_id": str(reference_id), "reference_type": reference_type},
        commit=False,
    )


class DeliveryBoyOrderService:

    # ── Profile ───────────────────────────────────────────

    @staticmethod
    def get_profile(db: Session, delivery_boy_id: str):
        boy = Repo.get_by_id(db, delivery_boy_id)
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")
        return {"success": True, "profile": DeliveryBoyProfileResponse.model_validate(boy)}

    @staticmethod
    def update_profile(db: Session, delivery_boy_id: str, payload):
        boy = Repo.get_by_id(db, delivery_boy_id)
        if not boy:
            raise HTTPException(status_code=404, detail="Delivery boy not found")

        update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
        boy = Repo.update(db, boy, update_data)
        return {
            "success": True,
            "message": "Profile updated",
            "profile": DeliveryBoyProfileResponse.model_validate(boy),
        }

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

        order, user, address, subscription, vendor = row

        sp_rows = Repo.get_subscription_packages_for_order(db, subscription.subscription_id)
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
            "packages": packages,
            "vendor": vendor
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
            "order_id": order.order_id,
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
            .filter(SubscriptionPackage.subscription_reference_id == order.subscription_reference_id)
            .all()
        )
        order_amount = sum(
            Decimal(str(sp.unit_price)) * sp.quantity for sp in sub_packages
        )
        if order_amount > 0:
            wallet = ProviderWalletRepository.get_or_create(db, order.vendor_reference_id)
            balance_before = Decimal(str(wallet.balance))
            ProviderWalletRepository.credit(db, wallet, order_amount)
            ProviderWalletRepository.create_transaction(db, {
                "wallet_reference_id": wallet.provider_wallet_id,
                "provider_reference_id": order.vendor_reference_id,
                "type": "credit",
                "reason": "order_delivered",
                "amount": order_amount,
                "balance_before": balance_before,
                "balance_after": Decimal(str(wallet.balance)),
                "reference_id": order.order_id,
                "reference_type": "order",
                "description": f"Delivery confirmed for {order.order_date} ({order.meal_slot})",
            })

        # Pay the delivery boy for the completed drop
        _credit_delivery_boy_for_delivery(
            db,
            delivery_boy_id,
            reference_id=order.order_id,
            reference_type="order",
            description=f"Order delivered on {order.order_date} ({order.meal_slot})",
        )

        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "message": "Order delivered successfully",
            "order_id": order.order_id,
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

        order, user, address, package, vendor = row

        return {
            "success": True,
            "order": order,
            "user": user,
            "delivery_address": address,
            "package_name": package.package_name,
            "vendor": vendor
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
            "order_id": order.extra_order_id,
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
            wallet = ProviderWalletRepository.get_or_create(db, order.vendor_reference_id)
            balance_before = Decimal(str(wallet.balance))
            ProviderWalletRepository.credit(db, wallet, order_amount)
            ProviderWalletRepository.create_transaction(db, {
                "wallet_reference_id": wallet.provider_wallet_id,
                "provider_reference_id": order.vendor_reference_id,
                "type": "credit",
                "reason": "order_delivered",
                "amount": order_amount,
                "balance_before": balance_before,
                "balance_after": Decimal(str(wallet.balance)),
                "reference_id": order.extra_order_id,
                "reference_type": "extra_order",
                "description": f"Extra order delivered on {order.delivery_date} ({order.meal_slot})",
            })

        # Pay the delivery boy for the completed drop
        _credit_delivery_boy_for_delivery(
            db,
            delivery_boy_id,
            reference_id=order.extra_order_id,
            reference_type="extra_order",
            description=f"Extra order delivered on {order.delivery_date} ({order.meal_slot})",
        )

        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "message": "Extra order delivered successfully",
            "order_id": order.extra_order_id,
            "status": order.status
        }
