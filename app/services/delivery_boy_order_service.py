"""
Delivery partner app: profile, order lists, dashboard and assigned subscriptions.
The hand-over actions (pickup, deliver, ...) live in delivery_handover_service.
"""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.clock import now_utc, today_local
from app.core.errors import DomainError
from app.domain import vendor_partner
from app.domain.status import (
    IN_HAND_STATUSES,
    SUB_UNPICKED_STATUSES,
    EXTRA_UNPICKED_STATUSES,
    SUBSCRIPTION_STATUSES,
)
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.models.subscription_plan_model import SubscriptionPlan
from app.models.user_address_model import UserAddress
from app.models.user_model import User
from app.repositories.delivery_boy_repository import DeliveryBoyRepository as Repo
from app.schemas.delivery_boy_schema import DeliveryBoyProfileResponse
from app.services.delivery_handover_service import DeliveryHandoverService
from app.services.delivery_views import (
    _SLOT_RANK, _Lookups, _card, _date_window, _extra_view, _kitchen_address, _lookup, _sort_key, _sub_view,
)

SUBSCRIPTION_PAGE_MAX = 50
VENDOR_UPCOMING_DAYS = 7
_GONE = ("cancelled", "skipped")


def _kitchen_brief(row, p: Provider) -> dict:
    return {
        "provider_id": p.provider_id,
        "business_name": p.business_name,
        "owner_name": p.full_name,
        "mobile_number": p.mobile_number,
        "address": vendor_partner.kitchen_address(p),
        "area": p.area,
        "city": p.city,
        "pincode": p.pincode,
        "is_accepting_orders": bool(p.is_accepting_orders),
        "assigned_at": row.assigned_at,
    }


def _profile(db: Session, boy) -> dict:
    """The partner's profile with the kitchens Orleeno assigned them (read fresh on every call)."""
    kitchens = vendor_partner.partner_kitchens(db, boy.delivery_boy_id)
    return {
        **DeliveryBoyProfileResponse.model_validate(boy).model_dump(),
        "assigned_vendor_count": len(kitchens),
        "assigned_vendors": [
            {"provider_id": p.provider_id, "business_name": p.business_name, "area": p.area, "city": p.city}
            for _, p in kitchens
        ],
    }


class DeliveryBoyOrderService(DeliveryHandoverService):

    # ── Profile ───────────────────────────────────────────

    @staticmethod
    def get_profile(db: Session, delivery_boy_id: str):
        boy = Repo.get_by_id(db, delivery_boy_id)
        if not boy:
            raise DomainError("Delivery boy not found", 404)
        return {"success": True, "profile": _profile(db, boy)}

    @staticmethod
    def update_profile(db: Session, delivery_boy_id: str, payload):
        boy = Repo.get_by_id(db, delivery_boy_id)
        if not boy:
            raise DomainError("Delivery boy not found", 404)

        update_data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
        if update_data.get("is_online") and (boy.approval_status != "approved" or not boy.is_active):
            raise DomainError("You can go online once your application is approved")
        if update_data.get("vehicle_number"):
            update_data["vehicle_number"] = update_data["vehicle_number"].strip().upper()
        boy = Repo.update(db, boy, update_data)
        db.commit()
        return {
            "success": True,
            "message": "Profile updated",
            "profile": _profile(db, boy),
        }

    # ── Assigned kitchens ─────────────────────────────────

    @staticmethod
    def _kitchen_counts(db: Session, delivery_boy_id, provider_ids) -> dict:
        """Today's work per kitchen for this partner: to collect, ready, in hand, delivered."""
        today = today_local()
        counts = {pid: {"today_total": 0, "to_pickup": 0, "ready_for_pickup": 0, "in_hand": 0, "delivered": 0,
                        "upcoming": 0} for pid in provider_ids}
        if not provider_ids:
            return counts
        end = today + timedelta(days=VENDOR_UPCOMING_DAYS)
        for model, day_col, unpicked in (
            (Order, Order.order_date, SUB_UNPICKED_STATUSES),
            (ExtraOrder, ExtraOrder.delivery_date, EXTRA_UNPICKED_STATUSES),
        ):
            rows = db.query(model.vendor_reference_id, day_col, model.status).filter(
                model.delivery_boy_reference_id == delivery_boy_id,
                model.vendor_reference_id.in_(list(provider_ids)),
                day_col >= today, day_col <= end,
                model.status.notin_(_GONE),
            ).all()
            for pid, day, status in rows:
                c = counts[pid]
                if day > today:
                    if status in unpicked:
                        c["upcoming"] += 1
                    continue
                c["today_total"] += 1
                if status in unpicked:
                    c["to_pickup"] += 1
                    if status == "ready_for_pickup":
                        c["ready_for_pickup"] += 1
                elif status in IN_HAND_STATUSES:
                    c["in_hand"] += 1
                elif status == "delivered":
                    c["delivered"] += 1
        return counts

    @staticmethod
    def list_vendors(db: Session, delivery_boy_id: str):
        """Kitchens Orleeno assigned to this partner, with what is waiting at each today."""
        kitchens = vendor_partner.partner_kitchens(db, delivery_boy_id)
        counts = DeliveryBoyOrderService._kitchen_counts(db, delivery_boy_id, [p.provider_id for _, p in kitchens])
        subs = dict(
            db.query(Subscription.vendor_reference_id, func.count(Subscription.subscription_id))
            .filter(
                Subscription.delivery_boy_reference_id == delivery_boy_id,
                Subscription.status.in_(("active", "paused")),
            )
            .group_by(Subscription.vendor_reference_id)
            .all()
        )
        return {
            "success": True,
            "total": len(kitchens),
            "vendors": [
                {
                    **_kitchen_brief(row, p),
                    **counts.get(p.provider_id, {}),
                    "active_subscriptions": subs.get(p.provider_id, 0),
                }
                for row, p in kitchens
            ],
        }

    @staticmethod
    def get_vendor_detail(db: Session, delivery_boy_id: str, provider_id):
        row = (
            db.query(vendor_partner.DeliveryPartnerVendor)
            .filter(
                vendor_partner.DeliveryPartnerVendor.delivery_boy_reference_id == delivery_boy_id,
                vendor_partner.DeliveryPartnerVendor.provider_reference_id == provider_id,
                vendor_partner.DeliveryPartnerVendor.status == "active",
            )
            .first()
        )
        if row is None:
            # not one of this partner's kitchens (or no such kitchen)
            raise DomainError("Kitchen not found", 404)
        kitchen = db.query(Provider).filter(Provider.provider_id == provider_id).first()

        today = today_local()
        end = today + timedelta(days=VENDOR_UPCOMING_DAYS)
        subs = db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id, Order.vendor_reference_id == provider_id,
            Order.order_date >= today, Order.order_date <= end, Order.status.notin_(_GONE),
        ).all()
        extras = db.query(ExtraOrder).filter(
            ExtraOrder.delivery_boy_reference_id == delivery_boy_id, ExtraOrder.vendor_reference_id == provider_id,
            ExtraOrder.delivery_date >= today, ExtraOrder.delivery_date <= end, ExtraOrder.status.notin_(_GONE),
        ).all()
        lk = _Lookups(db, subs, extras)
        cards = sorted(
            [_card(o, "subscription", lk) for o in subs] + [_card(o, "extra", lk) for o in extras], key=_sort_key,
        )
        counts = DeliveryBoyOrderService._kitchen_counts(db, delivery_boy_id, [kitchen.provider_id])
        return {
            "success": True,
            "vendor": {
                **_kitchen_brief(row, kitchen),
                **counts.get(kitchen.provider_id, {}),
            },
            "today_orders": [c for c in cards if c["date"] == today],
            "upcoming_orders": [c for c in cards if c["date"] > today],
        }

    # ── Lists and details ─────────────────────────────────

    @staticmethod
    def list_orders(db: Session, delivery_boy_id: str, order_date: date = None, meal_slot: str = None,
                    status: str = None, from_date: date = None, to_date: date = None):
        start, end = _date_window(order_date, from_date, to_date)
        q = db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id,
            Order.order_date >= start,
            Order.order_date <= end,
        )
        if meal_slot:
            q = q.filter(Order.meal_slot == meal_slot)
        if status:
            q = q.filter(Order.status == status)
        orders = q.all()
        orders.sort(key=lambda o: (o.order_date, _SLOT_RANK.get(o.meal_slot, 9)))
        lk = _Lookups(db, orders, [])
        return {"success": True, "total": len(orders), "orders": [_sub_view(o, lk) for o in orders]}

    @staticmethod
    def get_order_detail(db: Session, delivery_boy_id: str, order_id):
        row = Repo.get_subscription_order_detail(db, order_id, delivery_boy_id)
        if not row:
            raise DomainError("Order not found", 404)
        order, user, address, subscription, vendor = row
        lk = _Lookups(db, [order], [])
        # the package actually packed (a holiday replacement kitchen cooks its own)
        packages = lk.meals.packages(order)
        return {
            "success": True,
            "order": _sub_view(order, lk),
            "user": user,
            "delivery_address": address,
            "packages": packages,
            "vendor": vendor,
        }

    @staticmethod
    def list_extra_orders(db: Session, delivery_boy_id: str, delivery_date: date = None, meal_slot: str = None,
                          status: str = None, from_date: date = None, to_date: date = None):
        start, end = _date_window(delivery_date, from_date, to_date)
        q = db.query(ExtraOrder).filter(
            ExtraOrder.delivery_boy_reference_id == delivery_boy_id,
            ExtraOrder.delivery_date >= start,
            ExtraOrder.delivery_date <= end,
        )
        if meal_slot:
            q = q.filter(ExtraOrder.meal_slot == meal_slot)
        if status:
            q = q.filter(ExtraOrder.status == status)
        orders = q.all()
        orders.sort(key=lambda o: (o.delivery_date, _SLOT_RANK.get(o.meal_slot, 9)))
        lk = _Lookups(db, [], orders)
        return {"success": True, "total": len(orders), "orders": [_extra_view(o, lk) for o in orders]}

    @staticmethod
    def get_extra_order_detail(db: Session, delivery_boy_id: str, order_id):
        row = Repo.get_extra_order_detail(db, order_id, delivery_boy_id)
        if not row:
            raise DomainError("Extra order not found", 404)
        order, user, address, package, vendor = row
        return {
            "success": True,
            "order": _extra_view(order, _Lookups(db, [], [order])),
            "user": user,
            "delivery_address": address,
            "package_name": package.package_name,
            "vendor": vendor,
        }

    # ── Dashboard ─────────────────────────────────────────

    @staticmethod
    def dashboard(db: Session, delivery_boy_id: str):
        today = today_local()
        subs = db.query(Order).filter(
            Order.delivery_boy_reference_id == delivery_boy_id, Order.order_date == today
        ).all()
        extras = db.query(ExtraOrder).filter(
            ExtraOrder.delivery_boy_reference_id == delivery_boy_id, ExtraOrder.delivery_date == today
        ).all()

        # The next delivery may be on a later day when today's work is done
        future_subs = (
            db.query(Order)
            .filter(
                Order.delivery_boy_reference_id == delivery_boy_id,
                Order.order_date > today,
                Order.status.in_(SUB_UNPICKED_STATUSES),
            )
            .order_by(Order.order_date.asc())
            .limit(6)
            .all()
        )
        future_extras = (
            db.query(ExtraOrder)
            .filter(
                ExtraOrder.delivery_boy_reference_id == delivery_boy_id,
                ExtraOrder.delivery_date > today,
                ExtraOrder.status.in_(EXTRA_UNPICKED_STATUSES),
            )
            .order_by(ExtraOrder.delivery_date.asc())
            .limit(6)
            .all()
        )

        lk = _Lookups(db, subs + future_subs, extras + future_extras)
        all_today = sorted(
            [_card(o, "subscription", lk) for o in subs] + [_card(o, "extra", lk) for o in extras],
            key=_sort_key,
        )
        # skipped / cancelled meals are no longer deliveries: counted, but not listed as work
        today_cards = [c for c in all_today if c["status"] not in _GONE]
        future_cards = sorted(
            [_card(o, "subscription", lk) for o in future_subs] + [_card(o, "extra", lk) for o in future_extras],
            key=_sort_key,
        )

        counts = {"total": 0, "pending": 0, "ready_for_pickup": 0, "picked_up": 0, "out_for_delivery": 0,
                  "delivered": 0, "cancelled": 0, "failed": 0}
        for c in all_today:
            status = c["status"]
            if status in ("cancelled", "skipped"):
                counts["cancelled"] += 1
                continue
            counts["total"] += 1
            if status == "delivered":
                counts["delivered"] += 1
            elif status in IN_HAND_STATUSES:
                counts["picked_up"] += 1
                if status == "out_for_delivery":
                    counts["out_for_delivery"] += 1
            else:
                counts["pending"] += 1
                if status == "ready_for_pickup":
                    counts["ready_for_pickup"] += 1
            if c["pickup_locked"] or c["delivery_locked"]:
                counts["failed"] += 1

        in_hand = [c for c in today_cards if c["status"] in IN_HAND_STATUSES]
        # on the road first, then the oldest pickup
        in_hand.sort(key=lambda c: (c["status"] != "out_for_delivery", c["picked_up_at"] or now_utc()))
        active = in_hand[0] if in_hand else None
        upcoming = [
            c for c in today_cards + future_cards
            if c["status"] in SUB_UNPICKED_STATUSES + EXTRA_UNPICKED_STATUSES and not c["pickup_locked"]
        ]
        next_up = upcoming[0] if upcoming else None

        assigned_subscriptions = db.query(func.count(Subscription.subscription_id)).filter(
            Subscription.delivery_boy_reference_id == delivery_boy_id,
            Subscription.status.in_(("active", "paused")),
        ).scalar() or 0
        kitchens = vendor_partner.partner_kitchens(db, delivery_boy_id)

        return {
            "success": True,
            "date": today,
            "counts": counts,
            "active_delivery": active,
            "other_in_hand": in_hand[1:],
            "next_delivery": next_up,
            "today_orders": today_cards,
            "assigned_subscriptions": assigned_subscriptions,
            "assigned_vendor_count": len(kitchens),
            "assigned_vendors": [
                {"provider_id": p.provider_id, "business_name": p.business_name, "area": p.area}
                for _, p in kitchens
            ],
        }

    # ── Assigned subscriptions ────────────────────────────

    @staticmethod
    def list_subscriptions(db: Session, delivery_boy_id: str, status: str | None = None,
                           search: str | None = None, page: int = 1, limit: int = 20):
        limit = max(1, min(limit, SUBSCRIPTION_PAGE_MAX))
        if status in (None, "", "current"):
            statuses = ("active", "paused")
        elif status in SUBSCRIPTION_STATUSES:
            statuses = (status,)
        else:
            raise DomainError(f"status must be current or one of: {', '.join(SUBSCRIPTION_STATUSES)}")

        q = db.query(Subscription).filter(
            Subscription.delivery_boy_reference_id == delivery_boy_id,
            Subscription.status.in_(statuses),
        )
        if search:
            pattern = f"%{search.strip()}%"
            q = (
                q.join(User, User.user_id == Subscription.user_reference_id)
                .join(Provider, Provider.provider_id == Subscription.vendor_reference_id)
                .filter(or_(User.full_name.ilike(pattern), Provider.business_name.ilike(pattern)))
            )
        total = q.count()
        subs = q.order_by(Subscription.start_date.desc()).offset((page - 1) * limit).limit(limit).all()
        ids = [s.subscription_id for s in subs]

        today = today_local()
        stats = defaultdict(lambda: {"today": 0, "pending": 0, "in_progress": 0, "completed": 0, "cancelled": 0})
        next_meal: dict = {}
        if ids:
            rows = db.query(Order).filter(
                Order.subscription_reference_id.in_(ids),
                Order.delivery_boy_reference_id == delivery_boy_id,
            ).all()
            for o in rows:
                st = stats[o.subscription_reference_id]
                if o.status in ("cancelled", "skipped"):
                    st["cancelled"] += 1
                    continue
                if o.order_date == today:
                    st["today"] += 1
                if o.status == "delivered":
                    st["completed"] += 1
                elif o.status in IN_HAND_STATUSES:
                    st["in_progress"] += 1
                elif o.order_date >= today:
                    st["pending"] += 1
                    key = (o.order_date, _SLOT_RANK.get(o.meal_slot, 9))
                    best = next_meal.get(o.subscription_reference_id)
                    if best is None or key < best[0]:
                        next_meal[o.subscription_reference_id] = (key, o)

        users = _lookup(db, User, "user_id", (s.user_reference_id for s in subs))
        kitchens = _lookup(db, Provider, "provider_id", (s.vendor_reference_id for s in subs))
        addresses = _lookup(db, UserAddress, "user_address_id", (s.user_address_reference_id for s in subs))
        packages = defaultdict(list)
        if ids:
            for sp, mp in (
                db.query(SubscriptionPackage, MenuPackage)
                .join(MenuPackage, MenuPackage.package_id == SubscriptionPackage.package_reference_id)
                .filter(SubscriptionPackage.subscription_reference_id.in_(ids))
            ):
                packages[sp.subscription_reference_id].append({"package_name": mp.package_name, "quantity": sp.quantity})

        items = []
        for s in subs:
            user = users.get(s.user_reference_id)
            kitchen = kitchens.get(s.vendor_reference_id)
            address = addresses.get(s.user_address_reference_id)
            nxt = next_meal.get(s.subscription_id)
            items.append({
                "subscription_id": s.subscription_id,
                "status": s.status,
                "customer_name": user.full_name if user else None,
                "vendor_name": kitchen.business_name if kitchen else None,
                "delivery_area": f"{address.city} {address.pin_code}" if address else None,
                "subscription_type": s.subscription_type,
                "meal_slot": s.meal_slot,
                "start_date": s.start_date,
                "end_date": s.end_date,
                "packages": packages.get(s.subscription_id, []),
                "today_orders": stats[s.subscription_id]["today"],
                "pending_orders": stats[s.subscription_id]["pending"],
                "in_progress_orders": stats[s.subscription_id]["in_progress"],
                "completed_orders": stats[s.subscription_id]["completed"],
                "cancelled_orders": stats[s.subscription_id]["cancelled"],
                "next_order": {
                    "order_id": nxt[1].order_id,
                    "date": nxt[1].order_date,
                    "meal_slot": nxt[1].meal_slot,
                    "status": nxt[1].status,
                } if nxt else None,
            })
        return {"success": True, "total": total, "page": page, "subscriptions": items}

    @staticmethod
    def get_subscription_detail(db: Session, delivery_boy_id: str, subscription_id):
        sub = db.query(Subscription).filter(
            Subscription.subscription_id == subscription_id,
            Subscription.delivery_boy_reference_id == delivery_boy_id,
        ).first()
        if sub is None:
            # not assigned to this partner (or no such subscription)
            raise DomainError("Subscription not found", 404)

        user = db.query(User).filter(User.user_id == sub.user_reference_id).first()
        address = db.query(UserAddress).filter(UserAddress.user_address_id == sub.user_address_reference_id).first()
        kitchen = db.query(Provider).filter(Provider.provider_id == sub.vendor_reference_id).first()
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.subscription_plan_id == sub.plan_reference_id).first()
        packages = [
            {"package_name": mp.package_name, "quantity": sp.quantity}
            for sp, mp in Repo.get_subscription_packages_for_order(db, sub.subscription_id)
        ]

        orders = db.query(Order).filter(
            Order.subscription_reference_id == sub.subscription_id,
            Order.delivery_boy_reference_id == delivery_boy_id,
        ).all()
        lk = _Lookups(db, orders, [])
        today = today_local()
        cards = sorted((_card(o, "subscription", lk) for o in orders), key=_sort_key)

        counts = defaultdict(int)
        next_marked = False
        for c in cards:
            status = c["status"]
            if status == "delivered":
                group = "completed"
            elif status in ("cancelled", "skipped"):
                group = "cancelled"
            elif c["pickup_locked"] or c["delivery_locked"]:
                group = "failed"
            elif c["date"] < today:
                group = "missed"
            elif c["date"] == today:
                group = "today"
            else:
                group = "upcoming"
            c["group"] = group
            c["is_active"] = status in IN_HAND_STATUSES and group == "today"
            c["is_next"] = False
            if not next_marked and group in ("today", "upcoming") and status in SUB_UNPICKED_STATUSES:
                c["is_next"] = True
                next_marked = True
            counts[group] += 1

        return {
            "success": True,
            "subscription": {
                "subscription_id": sub.subscription_id,
                "status": sub.status,
                "subscription_type": sub.subscription_type,
                "meal_slot": sub.meal_slot,
                "plan_duration_days": plan.duration_days if plan else None,
                "start_date": sub.start_date,
                "end_date": sub.end_date,
                "last_meal_date": sub.end_date - timedelta(days=1),
                "packages": packages,
            },
            "customer": {
                "full_name": user.full_name if user else None,
                "phone": user.phone if user else None,
            },
            "delivery_address": {
                "address_line1": address.address_line1,
                "address_line2": address.address_line2,
                "landmark": address.landmark,
                "city": address.city,
                "state": address.state,
                "pin_code": address.pin_code,
                "latitude": address.latitude,
                "longitude": address.longitude,
            } if address else None,
            "kitchen": {
                "provider_id": kitchen.provider_id,
                "business_name": kitchen.business_name,
                "mobile_number": kitchen.mobile_number,
                "address": _kitchen_address(kitchen),
            } if kitchen else None,
            "counts": {
                "total": len(cards),
                "today": counts["today"],
                "upcoming": counts["upcoming"],
                "completed": counts["completed"],
                "cancelled": counts["cancelled"],
                "failed": counts["failed"],
                "missed": counts["missed"],
            },
            "orders": cards,
        }
