"""
Central pricing engine.

Every amount a customer pays and every amount a kitchen, delivery partner or
Orleeno earns is computed here, from:

  * the package price set by the kitchen (or Orleeno for catalogue packages),
  * the subscription plan discount (subscriptions only),
  * the admin-configured pricing components (master.pricing_components).

Terminology (fixed across the platform):
  price            base / MRP shown struck through
  discounted_price the SELLING price for one-time orders (<= price); NULL
                   means no discount. It is NOT a discount amount.
  subscription_price per-meal price when bought on a subscription; NULL
                   falls back to the selling price.
  discount_amount  price - selling price (derived, display only)

A quote is frozen into the order / subscription as `pricing_snapshot`; later
admin price changes never alter it. Settlement (earnings on delivery) and
refunds read the snapshot, not the current configuration.

Business rules (current phase):
  customer payable  = food amount + customer-facing charges
  food amount       = base amount - plan discount
  kitchen earning   = base unit price x quantity, per delivered meal
                      (the plan discount is funded by Orleeno)
  partner earning   = delivery_partner_payout component, per delivery
  Orleeno revenue   = commission + customer-facing charges
                      - partner payout - plan discount
Percentages are applied to the food amount. Every component is rounded
half-up to the paisa.
"""

from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

from sqlalchemy.orm import Session

from app.core.clock import now_utc
from app.core.errors import DomainError
from app.models.pricing_component_model import PricingComponent

PAISA = Decimal("0.01")
ZERO = Decimal("0.00")

COMPONENT_KEYS = (
    "sms_charge",
    "payment_gateway_charge",
    "packaging_charge",
    "delivery_charge",
    "platform_commission",
    "delivery_partner_payout",
)

PARTNER_PAYOUT_KEY = "delivery_partner_payout"


def money(value) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(PAISA, rounding=ROUND_HALF_UP)


def floor_money(value) -> Decimal:
    return Decimal(str(value)).quantize(PAISA, rounding=ROUND_DOWN)


# ── Package prices ────────────────────────────────────────────

def selling_price(package) -> Decimal:
    base = money(package.price)
    sell = package.discounted_price
    if sell is not None:
        sell = money(sell)
        if ZERO < sell <= base:
            return sell
    return base


def subscription_unit_price(package) -> Decimal:
    sub = package.subscription_price
    if sub is not None and money(sub) > ZERO:
        return money(sub)
    return selling_price(package)


def package_price_view(package) -> dict:
    """Unambiguous price fields every API returns for a package."""
    base = money(package.price)
    sell = selling_price(package)
    return {
        "base_price": base,
        "selling_price": sell,
        "discount_amount": base - sell,
        "subscription_unit_price": subscription_unit_price(package),
    }


def validate_package_prices(price, discounted_price, subscription_price) -> None:
    if price is None or money(price) <= ZERO:
        raise DomainError("Price must be greater than 0")
    if discounted_price is not None:
        d = money(discounted_price)
        if d <= ZERO:
            raise DomainError("Selling (discounted) price must be greater than 0, or left empty")
        if d > money(price):
            raise DomainError("Selling (discounted) price cannot be more than the price")
    if subscription_price is not None:
        s = money(subscription_price)
        if s <= ZERO:
            raise DomainError("Subscription price must be greater than 0, or left empty")
        if s > money(price):
            raise DomainError("Subscription price per meal cannot be more than the price")


# ── Configuration ─────────────────────────────────────────────

def current_components(db: Session) -> list[PricingComponent]:
    return (
        db.query(PricingComponent)
        .filter(PricingComponent.superseded_at.is_(None))
        .order_by(PricingComponent.component_key)
        .all()
    )


def _applies(component: PricingComponent, kind: str) -> bool:
    return component.is_active and component.applies_to in ("all", kind)


def _component_amount(component, *, food_amount: Decimal, units: int, deliveries: int, include_per_order: bool,
                      include_per_delivery: bool = True) -> Decimal:
    value = Decimal(str(component.value))
    if component.calc_type == "percentage":
        return money(food_amount * value / Decimal(100))
    basis = component.charge_basis
    if basis == "per_unit":
        return money(value * units)
    if basis == "per_delivery":
        return money(value * deliveries) if include_per_delivery else ZERO
    # per_order: once per checkout
    return money(value) if include_per_order else ZERO


def build_quote(
    components: list[PricingComponent],
    *,
    kind: str,
    base_unit_price: Decimal,
    quantity: int,
    deliveries: int,
    discount_percent=0,
    include_per_order: bool = True,
    include_per_delivery: bool = True,
) -> dict:
    """
    Price `quantity` units delivered `deliveries` times.

    kind: 'subscription' or 'extra_order'. Returns a JSON-serialisable dict
    (decimals as strings) that is stored as the pricing snapshot.

    A one-time checkout with several packages is ONE trip: its first line
    carries the per-order and per-delivery charges (delivery charge, partner
    payout) and the other lines pass include_per_order / include_per_delivery
    = False.
    """

    if quantity < 1 or deliveries < 1:
        raise DomainError("Quantity and number of meals must be at least 1")

    base_unit_price = money(base_unit_price)
    units = quantity * deliveries
    base_amount = money(base_unit_price * units)
    discount_percent = Decimal(str(discount_percent or 0))
    discount_amount = money(base_amount * discount_percent / Decimal(100))
    food_amount = base_amount - discount_amount

    charges = []
    partner_payout_total = ZERO
    commission = ZERO

    for component in components:
        if not _applies(component, kind):
            continue
        amount = _component_amount(
            component,
            food_amount=food_amount,
            units=units,
            deliveries=deliveries,
            include_per_order=include_per_order,
            include_per_delivery=include_per_delivery,
        )
        if component.component_key == PARTNER_PAYOUT_KEY:
            partner_payout_total = amount
            continue
        if not component.is_customer_facing:
            continue
        if component.component_key == "platform_commission":
            commission = amount
        charges.append({
            "key": component.component_key,
            "label": component.label,
            "calc_type": component.calc_type,
            "value": str(money(component.value)),
            "basis": component.charge_basis,
            "amount": str(amount),
            "version": component.version,
        })

    charges_amount = sum((Decimal(c["amount"]) for c in charges), ZERO)
    total_payable = food_amount + charges_amount

    provider_earning_per_delivery = money(base_unit_price * quantity)
    provider_earning_total = money(provider_earning_per_delivery * deliveries)

    platform_revenue = charges_amount - partner_payout_total - discount_amount

    return {
        "kind": kind,
        "priced_at": now_utc().isoformat(),
        "base_unit_price": str(base_unit_price),
        "quantity": quantity,
        "deliveries": deliveries,
        "units": units,
        "base_amount": str(base_amount),
        "discount_percent": str(discount_percent),
        "discount_amount": str(discount_amount),
        "food_amount": str(food_amount),
        "charges": charges,
        "charges_amount": str(charges_amount),
        "commission_amount": str(commission),
        "total_payable": str(total_payable),
        "settlement": {
            "provider_earning_total": str(provider_earning_total),
            "provider_earning_per_delivery": str(provider_earning_per_delivery),
            "partner_payout_total": str(partner_payout_total),
            "partner_payout_per_delivery": str(money(partner_payout_total / deliveries)),
            "customer_payable_per_delivery": str(floor_money(total_payable / deliveries)),
            "plan_discount_per_delivery": str(money(discount_amount / deliveries)),
            "charges_per_delivery": {
                c["key"]: str(money(Decimal(c["amount"]) / deliveries)) for c in charges
            },
            "platform_revenue_total": str(platform_revenue),
        },
    }


def quote_view(snapshot: dict) -> dict:
    """Customer-safe breakdown: no partner payout or platform margins."""
    return {
        "base_unit_price": snapshot["base_unit_price"],
        "quantity": snapshot["quantity"],
        "meals": snapshot["deliveries"],
        "base_amount": snapshot["base_amount"],
        "discount_percent": snapshot["discount_percent"],
        "discount_amount": snapshot["discount_amount"],
        "food_amount": snapshot["food_amount"],
        "charges": [
            {"key": c["key"], "label": c["label"], "amount": c["amount"]}
            for c in snapshot["charges"]
        ],
        "charges_amount": snapshot["charges_amount"],
        "total_payable": snapshot["total_payable"],
    }


def customer_payable_per_delivery(snapshot: dict | None, fallback_total, fallback_deliveries: int) -> Decimal:
    """Value of one meal to the customer, for skip / cancel refunds."""
    if snapshot and snapshot.get("settlement", {}).get("customer_payable_per_delivery") is not None:
        return Decimal(snapshot["settlement"]["customer_payable_per_delivery"])
    deliveries = max(int(fallback_deliveries or 1), 1)
    return floor_money(Decimal(str(fallback_total or 0)) / deliveries)
