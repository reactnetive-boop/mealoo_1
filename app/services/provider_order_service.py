from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.extra_order_repository import ExtraOrderRepository
from app.repositories.provider_wallet_repository import ProviderWalletRepository
from app.models.order_model import Order
from app.models.subscription_package_model import SubscriptionPackage
from app.models.subscription_model import Subscription
from app.models.menu_package_item_model import MenuPackageItem
from app.models.extra_order_model import ExtraOrder


class ProviderOrderService:

    # ── Subscriptions ─────────────────────────────────────

    @staticmethod
    def list_subscriptions(
        db: Session,
        vendor_id: str,
        status: str = None
    ):
        subs = SubscriptionRepository.get_all_by_vendor(
            db, vendor_id, status=status
        )
        return {
            "success": True,
            "total": len(subs),
            "subscriptions": subs
        }

    @staticmethod
    def get_subscription_detail(
        db: Session,
        vendor_id: str,
        subscription_id: str
    ):
        sub = SubscriptionRepository.get_by_id_and_vendor(
            db, subscription_id, vendor_id
        )
        if not sub:
            raise HTTPException(status_code=404, detail="Subscription not found")

        orders = SubscriptionRepository.get_orders_by_subscription(
            db, subscription_id
        )
        return {
            "success": True,
            "subscription": sub,
            "orders": orders
        }

    # ── Subscription Orders ───────────────────────────────

    @staticmethod
    def list_subscription_orders(
        db: Session,
        vendor_id: str,
        order_date: date = None,
        status: str = None
    ):
        orders = SubscriptionRepository.get_orders_by_vendor(
            db, vendor_id, order_date=order_date, status=status
        )
        return {
            "success": True,
            "total": len(orders),
            "orders": orders
        }

    @staticmethod
    def update_subscription_order_status(
        db: Session,
        vendor_id: str,
        order_id: str,
        new_status: str
    ):
        VALID_STATUSES = [
            "scheduled", "preparing",
            "out_for_delivery", "delivered",
            "skipped", "cancelled"
        ]
        if new_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"
            )

        order = SubscriptionRepository.get_order_by_id_and_vendor(
            db, order_id, vendor_id
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        prev_status = order.status
        order.status = new_status

        # Credit provider wallet when an order is first marked delivered
        if new_status == "delivered" and prev_status != "delivered":
            sub = db.query(Subscription).filter(
                Subscription.subscription_id == order.subscription_reference_id
            ).first()
            if sub:
                sub_packages = (
                    db.query(SubscriptionPackage)
                    .filter(SubscriptionPackage.subscription_reference_id == sub.subscription_id)
                    .all()
                )
                order_amount = sum(
                    Decimal(str(sp.unit_price)) * sp.quantity
                    for sp in sub_packages
                )
                if order_amount > 0:
                    wallet = ProviderWalletRepository.get_or_create(db, vendor_id)
                    balance_before = Decimal(str(wallet.balance))
                    ProviderWalletRepository.credit(db, wallet, order_amount)
                    ProviderWalletRepository.create_transaction(db, {
                        "wallet_reference_id": wallet.provider_wallet_id,
                        "provider_reference_id": vendor_id,
                        "type": "credit",
                        "reason": "order_delivered",
                        "amount": order_amount,
                        "balance_before": balance_before,
                        "balance_after": Decimal(str(wallet.balance)),
                        "reference_id": order.order_id,
                        "reference_type": "order",
                        "description": f"Earnings for order on {order.order_date} ({order.meal_slot})",
                    })

        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "message": f"Order status updated to '{new_status}'",
            "order_id": str(order.order_id),
            "status": order.status
        }

    # ── Extra Orders ──────────────────────────────────────

    @staticmethod
    def list_extra_orders(
        db: Session,
        vendor_id: str,
        delivery_date: date = None,
        status: str = None
    ):
        orders = ExtraOrderRepository.get_all_by_vendor(
            db, vendor_id, delivery_date=delivery_date, status=status
        )
        return {
            "success": True,
            "total": len(orders),
            "orders": orders
        }

    @staticmethod
    def update_extra_order_status(
        db: Session,
        vendor_id: str,
        order_id: str,
        new_status: str
    ):
        VALID_STATUSES = [
            "pending", "confirmed", "preparing",
            "out_for_delivery", "delivered", "cancelled"
        ]
        if new_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"
            )

        order = ExtraOrderRepository.get_by_id_and_vendor(
            db, order_id, vendor_id
        )
        if not order:
            raise HTTPException(status_code=404, detail="Extra order not found")

        prev_status = order.status
        order.status = new_status

        # Credit provider wallet when an extra order is first marked delivered
        if new_status == "delivered" and prev_status != "delivered":
            order_amount = Decimal(str(order.total_price))
            if order_amount > 0:
                wallet = ProviderWalletRepository.get_or_create(db, vendor_id)
                balance_before = Decimal(str(wallet.balance))
                ProviderWalletRepository.credit(db, wallet, order_amount)
                ProviderWalletRepository.create_transaction(db, {
                    "wallet_reference_id": wallet.provider_wallet_id,
                    "provider_reference_id": vendor_id,
                    "type": "credit",
                    "reason": "order_delivered",
                    "amount": order_amount,
                    "balance_before": balance_before,
                    "balance_after": Decimal(str(wallet.balance)),
                    "reference_id": order.extra_order_id,
                    "reference_type": "extra_order",
                    "description": f"Earnings for extra order on {order.delivery_date} ({order.meal_slot})",
                })

        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "message": f"Extra order status updated to '{new_status}'",
            "order_id": str(order.extra_order_id),
            "status": order.status
        }

    # ── Daily Food Calculator ─────────────────────────────

    @staticmethod
    def get_daily_food_summary(
        db: Session,
        vendor_id: str,
        summary_date: date,
        meal_slot: str = None
    ):
        # ── Subscription orders ──────────────────────────
        sub_order_query = db.query(Order).filter(
            Order.vendor_reference_id == vendor_id,
            Order.order_date == summary_date,
            Order.status.notin_(["cancelled", "skipped"])
        )
        if meal_slot:
            sub_order_query = sub_order_query.filter(Order.meal_slot == meal_slot)
        sub_orders = sub_order_query.all()

        # item_name → quantity_description → total_count
        tally: dict = defaultdict(lambda: defaultdict(int))

        if sub_orders:
            subscription_ids = list({o.subscription_reference_id for o in sub_orders})

            sub_packages = (
                db.query(SubscriptionPackage)
                .filter(SubscriptionPackage.subscription_reference_id.in_(subscription_ids))
                .all()
            )

            # subscription_id → [(package_id, qty_per_subscription)]
            sub_pkg_map: dict = defaultdict(list)
            for sp in sub_packages:
                sub_pkg_map[sp.subscription_reference_id].append((sp.package_reference_id, sp.quantity))

            package_ids = list({sp.package_reference_id for sp in sub_packages})

            pkg_items = (
                db.query(MenuPackageItem)
                .filter(MenuPackageItem.package_reference_id.in_(package_ids))
                .all()
            )

            # package_id → [MenuPackageItem]
            pkg_item_map: dict = defaultdict(list)
            for item in pkg_items:
                pkg_item_map[item.package_reference_id].append(item)

            for order in sub_orders:
                for pkg_id, pkg_qty in sub_pkg_map[order.subscription_reference_id]:
                    for item in pkg_item_map[pkg_id]:
                        tally[item.item_name][item.quantity or ""] += pkg_qty

        # ── Extra orders ─────────────────────────────────
        extra_query = db.query(ExtraOrder).filter(
            ExtraOrder.vendor_reference_id == vendor_id,
            ExtraOrder.delivery_date == summary_date,
            ExtraOrder.status != "cancelled"
        )
        if meal_slot:
            extra_query = extra_query.filter(ExtraOrder.meal_slot == meal_slot)
        extra_orders = extra_query.all()

        if extra_orders:
            extra_pkg_ids = list({eo.package_reference_id for eo in extra_orders})

            extra_pkg_items = (
                db.query(MenuPackageItem)
                .filter(MenuPackageItem.package_reference_id.in_(extra_pkg_ids))
                .all()
            )

            extra_pkg_item_map: dict = defaultdict(list)
            for item in extra_pkg_items:
                extra_pkg_item_map[item.package_reference_id].append(item)

            for eo in extra_orders:
                for item in extra_pkg_item_map[eo.package_reference_id]:
                    tally[item.item_name][item.quantity or ""] += eo.quantity

        # ── Build response ────────────────────────────────
        items = []
        for item_name in sorted(tally.keys()):
            for qty_desc, total_servings in tally[item_name].items():
                items.append({
                    "item_name": item_name,
                    "quantity_per_serving": qty_desc,
                    "total_servings": total_servings
                })

        return {
            "success": True,
            "date": summary_date,
            "meal_slot": meal_slot or "all",
            "subscription_orders_count": len(sub_orders),
            "extra_orders_count": len(extra_orders),
            "total_orders_count": len(sub_orders) + len(extra_orders),
            "items": items
        }
