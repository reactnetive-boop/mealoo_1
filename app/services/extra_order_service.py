"""
One-time ("extra") orders.

Rules: the date is today (before the slot's cut-off) or up to
EXTRA_ORDER_MAX_DAYS_AHEAD days ahead, in the business timezone; every
package is sold by the chosen kitchen to the address pincode and served in
the chosen slot; the kitchen is not on holiday that day; package capacity and
the kitchen's daily limit hold under a kitchen row lock; prices come from the
pricing engine and are frozen per order; the wallet is debited once per
checkout (idempotent).
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.audit import business_event
from app.core.clock import today_local
from app.core.config import EXTRA_ORDER_MAX_DAYS_AHEAD
from app.core.errors import DomainError
from app.core.paging import FIRST_PAGE, Paging
from app.domain import capacity, checkout, ledger, notify, orders as meals
from app.domain.eligibility import assert_sellable, is_on_holiday
from app.domain.pricing import build_quote, current_components, quote_view, selling_price, money, ZERO
from app.domain.slots import package_serves, is_before_cutoff, SLOT_CUTOFFS, delivery_window
from app.domain.status import EXTRA_OPEN_STATUSES
from app.domain.verification import delivery_code, delivery_code_expired
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.repositories.cart_repository import CartRepository
from app.repositories.extra_order_repository import ExtraOrderRepository
from app.services.subscription_service import owned_address


def _merge_items(items) -> list[tuple]:
    merged: dict = {}
    for item in items:
        merged[str(item.package_id)] = merged.get(str(item.package_id), 0) + item.quantity
    for pid, qty in merged.items():
        if qty > 5:
            raise DomainError("At most 5 of the same package per order")
    return list(merged.items())


def _validate_date(delivery_date, slot: str) -> None:
    today = today_local()
    if delivery_date < today:
        raise DomainError("The delivery date is in the past")
    if delivery_date > today + timedelta(days=EXTRA_ORDER_MAX_DAYS_AHEAD):
        raise DomainError(f"Orders can be placed at most {EXTRA_ORDER_MAX_DAYS_AHEAD} days ahead")
    if not is_before_cutoff(delivery_date, slot):
        raise DomainError(
            f"Today's {slot} orders closed at {SLOT_CUTOFFS[slot].strftime('%I:%M %p').lstrip('0')}. "
            "Please choose another date or meal.",
            code="CUTOFF_PASSED",
        )


def order_view(order: ExtraOrder, package: MenuPackage | None = None, provider: Provider | None = None) -> dict:
    show_code = (
        order.delivery_date == today_local()
        and order.status in EXTRA_OPEN_STATUSES
        and not delivery_code_expired(order)
    )
    return {
        "extra_order_id": order.extra_order_id,
        "checkout_id": order.checkout_id,
        "user_reference_id": order.user_reference_id,
        "vendor_reference_id": order.vendor_reference_id,
        "vendor_name": provider.business_name if provider else None,
        "address_reference_id": order.address_reference_id,
        "package_reference_id": order.package_reference_id,
        "package_name": package.package_name if package else None,
        "quantity": order.quantity,
        "unit_price": order.unit_price,
        "charges_amount": order.charges_amount,
        "total_price": order.total_price,
        "price_breakdown": quote_view(order.pricing_snapshot) if order.pricing_snapshot else None,
        "delivery_date": order.delivery_date,
        "meal_slot": order.meal_slot,
        "status": order.status,
        "cancel_reason": order.cancel_reason,
        "refund_amount": order.refund_amount,
        "otp_for_delivery": delivery_code(order) if show_code else None,
        "delivery_window": delivery_window(order.meal_slot),
        "can_cancel": order.status == "pending" and is_before_cutoff(order.delivery_date, order.meal_slot),
        "delivered_at": order.delivered_at,
        "created_at": order.created_at,
    }


class ExtraOrderService:

    @staticmethod
    def _price(db: Session, user_id: str, payload, lock: bool):
        address = owned_address(db, user_id, payload.address_id)
        slot = payload.meal_slot.value
        _validate_date(payload.delivery_date, slot)

        lines = _merge_items(payload.items)
        components = current_components(db)
        priced = []
        provider = None
        for index, (package_id, qty) in enumerate(lines):
            provider, package = assert_sellable(
                db,
                provider_id=payload.vendor_id,
                package_id=package_id,
                delivery_pincode=address.pin_code,
                lock_provider=lock and index == 0,
            )
            if not package_serves(package.meal_type, [slot]):
                raise DomainError(f"'{package.package_name}' is not served for {slot}")
            snapshot = build_quote(
                components,
                kind="extra_order",
                base_unit_price=selling_price(package),
                quantity=qty,
                deliveries=1,
                # one checkout = one trip: trip charges and partner payout on the first line only
                include_per_order=(index == 0),
                include_per_delivery=(index == 0),
            )
            priced.append((package, qty, snapshot))

        if is_on_holiday(db, provider.provider_id, payload.delivery_date):
            raise DomainError(f"{provider.business_name} is closed on {payload.delivery_date}", code="KITCHEN_HOLIDAY")

        return address, slot, provider, priced

    @staticmethod
    def quote(db: Session, user_id: str, payload):
        _, slot, provider, priced = ExtraOrderService._price(db, user_id, payload, lock=False)
        total = sum((Decimal(s["total_payable"]) for _, _, s in priced), ZERO)
        balance = ledger.customer_balance(db, user_id)
        return {
            "success": True,
            "kind": "extra_order",
            "provider_id": provider.provider_id,
            "provider_name": provider.business_name,
            "delivery_date": payload.delivery_date,
            "meal_slot": slot,
            "items": [
                {"package_id": p.package_id, "package_name": p.package_name, "quantity": q, "breakdown": quote_view(s)}
                for p, q, s in priced
            ],
            "total_payable": total,
            "wallet_balance": balance,
            "shortfall": max(ZERO, total - balance),
        }

    @staticmethod
    def place_order(db: Session, user_id: str, payload, idempotency_key: str | None = None):

        txn_key = f"extra_payment:{user_id}:{idempotency_key}" if idempotency_key else None
        if txn_key:
            existing = ledger.customer_txn_exists(db, txn_key)
            if existing:
                orders = db.query(ExtraOrder).filter(ExtraOrder.checkout_id == existing.reference_id).all()
                return {
                    "success": True,
                    "message": "Order already placed",
                    "total_amount": existing.amount,
                    "wallet_balance_after": existing.balance_after,
                    "orders": [order_view(o) for o in orders],
                }

        address, slot, provider, priced = ExtraOrderService._price(db, user_id, payload, lock=True)

        for package, qty, _ in priced:
            capacity.assert_package_room(
                db, provider_id=provider.provider_id, package_id=package.package_id,
                package_name=package.package_name, slots=[slot],
                start=payload.delivery_date, end=payload.delivery_date, quantity=qty,
            )
        capacity.assert_kitchen_room(
            db, provider_id=provider.provider_id, slots=[slot],
            start=payload.delivery_date, end=payload.delivery_date,
            quantity=sum(q for _, q, _ in priced),
        )

        total = sum((Decimal(s["total_payable"]) for _, _, s in priced), ZERO)
        wallet = ledger.lock_customer_wallet(db, user_id)
        if txn_key:
            # re-check under the wallet lock: a concurrent retry may have just paid
            existing = ledger.customer_txn_exists(db, txn_key)
            if existing:
                db.rollback()
                orders = db.query(ExtraOrder).filter(ExtraOrder.checkout_id == existing.reference_id).all()
                return {
                    "success": True,
                    "message": "Order already placed",
                    "total_amount": existing.amount,
                    "wallet_balance_after": existing.balance_after,
                    "orders": [order_view(o) for o in orders],
                }
        if money(wallet.balance) < total:
            raise ledger.InsufficientBalance(total, money(wallet.balance))

        checkout_id = uuid.uuid4()
        codes = meals.new_codes(shared=True)  # one delivery, one code for every line
        created = []
        for package, qty, snapshot in priced:
            order = ExtraOrder(
                extra_order_id=uuid.uuid4(),
                checkout_id=checkout_id,
                user_reference_id=user_id,
                vendor_reference_id=provider.provider_id,
                address_reference_id=address.user_address_id,
                package_reference_id=package.package_id,
                quantity=qty,
                unit_price=Decimal(snapshot["base_unit_price"]),
                charges_amount=Decimal(snapshot["charges_amount"]),
                total_price=Decimal(snapshot["total_payable"]),
                pricing_snapshot=snapshot,
                delivery_date=payload.delivery_date,
                meal_slot=slot,
                status="pending",
                **codes,
            )
            db.add(order)
            created.append((order, package))
        db.flush()

        txn = ledger.post_customer(
            db, user_id,
            type="debit",
            amount=total,
            reason="order_placed",
            idempotency_key=txn_key or f"extra_payment:{checkout_id}",
            reference_type="extra_checkout",
            reference_id=checkout_id,
            description=f"One-time {slot} order for {payload.delivery_date} from {provider.business_name}",
            wallet=wallet,
        )

        CartRepository.delete_by_package_ids(db, user_id, [str(p.package_id) for p, _, _ in priced])
        notify.customer(
            db, user_id, "order_placed", "Order placed",
            f"Your {slot} order for {payload.delivery_date} is waiting for the kitchen to confirm.",
            {"checkout_id": str(checkout_id)},
        )
        cutoff = SLOT_CUTOFFS[slot].strftime("%I:%M %p").lstrip("0")
        notify.kitchen(
            db, provider.provider_id, "new_order", "New one-time order - please confirm",
            ", ".join(f"{p.package_name} x {q}" for p, q, _ in priced)
            + f" for {slot} on {payload.delivery_date}. Confirm it before {cutoff} that day or it is cancelled.",
            {"checkout_id": str(checkout_id), "kind": "extra", "delivery_date": str(payload.delivery_date)},
        )
        db.commit()
        business_event("extra_order.placed", checkout_id=checkout_id, user_id=user_id, amount=total)

        return {
            "success": True,
            "message": "Order placed successfully",
            "total_amount": total,
            "wallet_balance_after": txn.balance_after,
            "orders": [order_view(o, p, provider) for o, p in created],
        }

    @staticmethod
    def _owned(db: Session, user_id: str, order_id, lock=False) -> ExtraOrder:
        q = db.query(ExtraOrder).filter(ExtraOrder.extra_order_id == order_id, ExtraOrder.user_reference_id == user_id)
        if lock:
            q = q.with_for_update()
        order = q.first()
        if order is None:
            raise DomainError("Order not found", 404)
        return order

    @staticmethod
    def get_order_list(db: Session, user_id: str, paging: Paging = FIRST_PAGE):
        orders = ExtraOrderRepository.get_all_by_user(db, user_id, paging.offset, paging.limit)
        package_ids = {o.package_reference_id for o in orders}
        provider_ids = {o.vendor_reference_id for o in orders}
        packages = {p.package_id: p for p in db.query(MenuPackage).filter(MenuPackage.package_id.in_(package_ids)).all()} if package_ids else {}
        providers = {p.provider_id: p for p in db.query(Provider).filter(Provider.provider_id.in_(provider_ids)).all()} if provider_ids else {}
        return {
            "success": True,
            **paging.meta(ExtraOrderRepository.count_by_user(db, user_id)),
            "orders": [order_view(o, packages.get(o.package_reference_id), providers.get(o.vendor_reference_id)) for o in orders],
        }

    @staticmethod
    def get_order(db: Session, user_id: str, order_id):
        order = ExtraOrderService._owned(db, user_id, order_id)
        package = db.query(MenuPackage).filter(MenuPackage.package_id == order.package_reference_id).first()
        provider = db.query(Provider).filter(Provider.provider_id == order.vendor_reference_id).first()
        return order_view(order, package, provider)

    @staticmethod
    def cancel_order(db: Session, user_id: str, order_id):
        """Cancels the whole checkout (one delivery): every line the kitchen has not accepted yet."""
        order = ExtraOrderService._owned(db, user_id, order_id, lock=True)
        if order.status != "pending":
            raise DomainError("This order is already being prepared and can no longer be cancelled")
        if not is_before_cutoff(order.delivery_date, order.meal_slot):
            raise DomainError("The cut-off for this meal has passed")
        others = checkout.siblings(db, order)
        if any(o.status not in ("pending", "cancelled") for o in others):
            raise DomainError("The kitchen has already accepted part of this order, so it can no longer be cancelled")
        refund = ZERO
        for line in [order, *others]:
            if line.status != "pending":
                continue
            line.status = "cancelled"
            line.cancel_reason = "customer"
            refund += meals.refund_extra_order(
                db, line, reason="order_cancel_refund", description="Refund for cancelled one-time order"
            )
        notify.kitchen(
            db, order.vendor_reference_id, "order_cancelled", "One-time order cancelled",
            f"The customer cancelled their {order.meal_slot} order for {order.delivery_date}. No need to prepare it.",
            {"extra_order_id": str(order.extra_order_id), "kind": "extra_order"},
        )
        notify.delivery_partner(
            db, order.delivery_boy_reference_id, "schedule_update", "Delivery cancelled",
            f"The one-time {order.meal_slot} delivery on {order.delivery_date} was cancelled by the customer.",
            {"order_id": str(order.extra_order_id), "kind": "extra_order"},
        )
        db.commit()
        return {"success": True, "message": f"Order cancelled. Rs {refund} refunded to your wallet.", "refund_amount": refund}
