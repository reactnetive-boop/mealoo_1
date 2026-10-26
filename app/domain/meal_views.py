"""
What a subscription meal is and what changed about it - one answer for the
kitchen, delivery partner, customer and admin views.

Every view reads the meal row itself (subscription.orders), which every
change writes to: a skip sets status 'skipped'; a package or kitchen switch
cancels the old plan's future meals and creates the new plan's meals (from
the effective date, logged in package_switch_logs); a holiday moves a meal
to a replacement kitchen (vendor_reference_id, original_vendor_reference_id,
replacement_package_reference_id) or cancels it ('vendor_holiday' /
'vendor_emergency_holiday'). So a refresh always shows the latest state.

Tags (`change_tags`):
  SKIPPED                         the customer skipped it (not on any route)
  PACKAGE_SWITCHED                from a package switch: old -> new package
  VENDOR_CHANGED                  picked up from another kitchen: kitchen
                                  switch, or a holiday replacement
  NOT_DELIVERABLE_VENDOR_HOLIDAY  cancelled because the kitchen is closed
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.domain.status import TERMINAL_ORDER_STATUSES
from app.models.menu_package_model import MenuPackage
from app.models.order_model import Order
from app.models.package_switch_log_model import PackageSwitchLog
from app.models.provider_model import Provider
from app.models.subscription_package_model import SubscriptionPackage

SKIPPED = "SKIPPED"
PACKAGE_SWITCHED = "PACKAGE_SWITCHED"
VENDOR_CHANGED = "VENDOR_CHANGED"
NOT_DELIVERABLE = "NOT_DELIVERABLE_VENDOR_HOLIDAY"

LABELS = {
    SKIPPED: "SKIPPED",
    PACKAGE_SWITCHED: "PACKAGE SWITCHED",
    VENDOR_CHANGED: "VENDOR CHANGED",
    NOT_DELIVERABLE: "NOT DELIVERABLE – VENDOR HOLIDAY",
}

EMERGENCY_REASON = "vendor_emergency_holiday"
HOLIDAY_REASONS = (EMERGENCY_REASON, "vendor_holiday", "vendor_holiday_not_owed", "kitchen_holiday")


def _tag(kind: str, **extra) -> dict:
    return {"type": kind, "label": LABELS[kind], **extra}


class MealContext:
    """Packages, kitchens and switch history for a batch of meals, in a few queries."""

    def __init__(self, db: Session, orders):
        orders = [o for o in orders if o is not None]
        sub_ids = {o.subscription_reference_id for o in orders}
        self._packages: dict = defaultdict(list)
        names: dict = {}
        if sub_ids:
            for sp, mp in (
                db.query(SubscriptionPackage, MenuPackage)
                .join(MenuPackage, MenuPackage.package_id == SubscriptionPackage.package_reference_id)
                .filter(SubscriptionPackage.subscription_reference_id.in_(sub_ids))
            ):
                self._packages[sp.subscription_reference_id].append(
                    {"package_id": mp.package_id, "package_name": mp.package_name, "quantity": sp.quantity}
                )
                names[mp.package_id] = mp.package_name
        self._switches = {}
        if sub_ids:
            for log in db.query(PackageSwitchLog).filter(PackageSwitchLog.new_subscription_reference_id.in_(sub_ids)):
                self._switches[log.new_subscription_reference_id] = log
        extra_pkgs = {o.replacement_package_reference_id for o in orders if o.replacement_package_reference_id}
        extra_pkgs |= {log.old_package_reference_id for log in self._switches.values()}
        extra_pkgs -= set(names)
        if extra_pkgs:
            names.update(dict(
                db.query(MenuPackage.package_id, MenuPackage.package_name).filter(
                    MenuPackage.package_id.in_(list(extra_pkgs))
                )
            ))
        self._package_names = names
        kitchens = {o.vendor_reference_id for o in orders} | {
            o.original_vendor_reference_id for o in orders if o.original_vendor_reference_id
        }
        for log in self._switches.values():
            kitchens |= {log.old_provider_reference_id, log.new_provider_reference_id}
        kitchens.discard(None)
        self._kitchens = dict(
            db.query(Provider.provider_id, Provider.business_name).filter(Provider.provider_id.in_(list(kitchens)))
        ) if kitchens else {}

    def kitchen_name(self, provider_id) -> str | None:
        return self._kitchens.get(provider_id)

    def packages(self, o: Order) -> list[dict]:
        """What the kitchen cooks for this meal (the replacement package on a holiday move)."""
        base = self._packages.get(o.subscription_reference_id, [])
        if o.replacement_package_reference_id:
            qty = base[0]["quantity"] if base else 1
            return [{
                "package_id": o.replacement_package_reference_id,
                "package_name": self._package_names.get(o.replacement_package_reference_id),
                "quantity": qty,
                "is_replacement": True,
            }]
        return [{**p, "is_replacement": False} for p in base]

    def tags(self, o: Order) -> list[dict]:
        tags = []
        if o.status == "skipped":
            tags.append(_tag(SKIPPED))
        if o.status == "cancelled" and o.cancel_reason in HOLIDAY_REASONS:
            tags.append(_tag(NOT_DELIVERABLE, reason=o.cancel_reason))
        log = self._switches.get(o.subscription_reference_id)
        if log is not None and o.order_date >= log.effective_date:
            if log.old_package_reference_id != log.new_package_reference_id:
                tags.append(_tag(
                    PACKAGE_SWITCHED, effective_date=log.effective_date.isoformat(),
                    **{"from": self._package_names.get(log.old_package_reference_id),
                       "to": self._package_names.get(log.new_package_reference_id)},
                ))
            if log.old_provider_reference_id != log.new_provider_reference_id:
                tags.append(_tag(
                    VENDOR_CHANGED, reason="vendor_switch", effective_date=log.effective_date.isoformat(),
                    **{"from": self._kitchens.get(log.old_provider_reference_id),
                       "to": self._kitchens.get(log.new_provider_reference_id)},
                ))
        if o.original_vendor_reference_id and o.original_vendor_reference_id != o.vendor_reference_id:
            tags.append(_tag(
                VENDOR_CHANGED, reason="vendor_holiday",
                **{"from": self._kitchens.get(o.original_vendor_reference_id),
                   "to": self._kitchens.get(o.vendor_reference_id)},
            ))
        return tags

    def holiday_outcome(self, o: Order) -> dict | None:
        if o.status == "cancelled" and o.cancel_reason == EMERGENCY_REASON:
            return {
                "holiday_type": "emergency",
                "outcome": "compensated",
                "label": "Kitchen on leave – meal refunded to your wallet",
                "will_be_delivered": False,
                "skips_credited": 1,
                "wallet_credit": str(o.refund_amount) if o.refund_amount is not None else None,
            }
        if o.status == "cancelled" and o.cancel_reason in ("vendor_holiday", "vendor_holiday_not_owed"):
            return {
                "holiday_type": "casual",
                "outcome": "made_up_at_plan_end",
                "label": "Vendor holiday – no delivery",
                "will_be_delivered": False,
            }
        if o.original_vendor_reference_id and o.original_vendor_reference_id != o.vendor_reference_id:
            name = self._kitchens.get(o.vendor_reference_id)
            return {
                "holiday_type": "emergency",
                "outcome": "replaced",
                "label": f"Coming from {name or 'another kitchen'} at no extra cost",
                "will_be_delivered": o.status not in ("cancelled", "skipped"),
                "replacement_vendor_name": name,
                "original_vendor_name": self._kitchens.get(o.original_vendor_reference_id),
            }
        return None


def on_route(o) -> bool:
    """Still a delivery to make (not skipped, cancelled or finished)."""
    return o.status not in TERMINAL_ORDER_STATUSES
