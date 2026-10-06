"""
Who can sell what to whom.

A package is sellable to a customer only when ALL of these hold:
  kitchen active + approved + profile complete + accepting orders
  package approved + active + available + not deleted
  the kitchen offers the package (own package, or a catalogue package it
    selected)
  the kitchen's pincode is an active serviceable pincode, and the
    customer's delivery pincode is served by the kitchen: its own pincode or
    one of its service areas (provider_service_areas, set by Orleeno)
  (subscriptions) the package allows subscription
  (a given date) the kitchen is not on holiday that day

Listing, cart, subscription, extra order and switch all call these
functions, so the rules cannot drift between screens.
"""

from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.domain.status import EXTRA_OPEN_STATUSES
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.models.provider_service_area_model import ProviderServiceArea
from app.models.provider_unavailability_model import ProviderUnavailability
from app.models.serviceable_pincode_model import ServiceablePincode
from app.models.subscription_model import Subscription


def parse_pincode(value) -> int | None:
    try:
        pin = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return pin if 100000 <= pin <= 999999 else None


def serviceable_pincode(db: Session, pincode) -> ServiceablePincode | None:
    pin = parse_pincode(pincode)
    if pin is None:
        return None
    return (
        db.query(ServiceablePincode)
        .filter(ServiceablePincode.pincode == pin, ServiceablePincode.is_active == True)  # noqa: E712
        .first()
    )


def serves_pincode_filter(pin: int):
    """SQL filter: kitchens that deliver to `pin` (own pincode or a service area)."""
    return or_(
        Provider.pincode == pin,
        Provider.provider_id.in_(
            select(ProviderServiceArea.provider_reference_id).where(ProviderServiceArea.pincode == pin)
        ),
    )


def kitchen_serves(db: Session, provider: Provider, pin: int | None) -> bool:
    if pin is None:
        return False
    if pin == provider.pincode:
        return True
    return db.query(ProviderServiceArea.provider_service_area_id).filter(
        ProviderServiceArea.provider_reference_id == provider.provider_id,
        ProviderServiceArea.pincode == pin,
    ).first() is not None


def open_commitments(db: Session, provider_id) -> tuple[int, int]:
    """(running subscriptions, open one-time orders) a kitchen still has to serve."""
    subscriptions = db.query(Subscription).filter(
        Subscription.vendor_reference_id == provider_id,
        Subscription.status.in_(("active", "paused")),
    ).count()
    one_time = db.query(ExtraOrder).filter(
        ExtraOrder.vendor_reference_id == provider_id,
        ExtraOrder.status.in_(EXTRA_OPEN_STATUSES),
    ).count()
    return subscriptions, one_time


def assert_pincode_can_change(db: Session, provider, new_pincode: int) -> None:
    """
    A kitchen only serves its own pincode, so moving it would strand every
    customer it already sold to. The move waits until nothing is running.
    """
    if new_pincode == provider.pincode:
        return
    subscriptions, one_time = open_commitments(db, provider.provider_id)
    if subscriptions or one_time:
        raise DomainError(
            "The kitchen pincode cannot change while it has "
            f"{subscriptions} running subscription(s) and {one_time} open one-time order(s). "
            "Contact Orleeno support to move the kitchen.",
            409,
            code="KITCHEN_HAS_OPEN_ORDERS",
        )


def provider_block_reason(provider: Provider | None) -> str | None:
    if provider is None:
        return "Kitchen not found"
    if not provider.is_active:
        return "This kitchen is currently inactive"
    if provider.approval_status != "approved":
        return "This kitchen is not approved yet"
    if not provider.is_profile_completed:
        return "This kitchen has not completed its profile"
    if not provider.is_accepting_orders:
        return "This kitchen is not accepting orders right now"
    return None


def package_block_reason(package: MenuPackage | None) -> str | None:
    if package is None or package.deleted_at is not None:
        return "Package not found"
    if package.approval_status != "approved":
        return "This package is not approved yet"
    if not package.is_active:
        return "This package is not active"
    if not package.is_available:
        return "This package is currently unavailable"
    return None


def provider_sellable_filter():
    """SQLAlchemy filter for kitchens customers may buy from."""
    return and_(
        Provider.is_active == True,  # noqa: E712
        Provider.approval_status == "approved",
        Provider.is_profile_completed == True,  # noqa: E712
        Provider.is_accepting_orders == True,  # noqa: E712
    )


def package_sellable_filter():
    return and_(
        MenuPackage.approval_status == "approved",
        MenuPackage.is_active == True,  # noqa: E712
        MenuPackage.is_available == True,  # noqa: E712
        MenuPackage.deleted_at.is_(None),
    )


def offering(db: Session, provider_id, package_id) -> ProviderSelectedPackage | None:
    return (
        db.query(ProviderSelectedPackage)
        .filter(
            ProviderSelectedPackage.provider_id == provider_id,
            ProviderSelectedPackage.package_id == package_id,
            ProviderSelectedPackage.is_active == True,  # noqa: E712
        )
        .first()
    )


def is_on_holiday(db: Session, provider_id, on: date) -> bool:
    return (
        db.query(ProviderUnavailability.provider_unavailability_id)
        .filter(
            ProviderUnavailability.provider_reference_id == provider_id,
            ProviderUnavailability.unavailable_date == on,
        )
        .first()
        is not None
    )


def kitchens_on_holiday(db: Session, provider_ids, on: date) -> set:
    """The subset of `provider_ids` closed on `on` (one query for a whole list)."""
    if not provider_ids:
        return set()
    rows = (
        db.query(ProviderUnavailability.provider_reference_id)
        .filter(
            ProviderUnavailability.provider_reference_id.in_(list(provider_ids)),
            ProviderUnavailability.unavailable_date == on,
        )
        .all()
    )
    return {r[0] for r in rows}


def assert_sellable(
    db: Session,
    *,
    provider_id,
    package_id,
    delivery_pincode=None,
    for_subscription: bool = False,
    lock_provider: bool = False,
) -> tuple[Provider, MenuPackage]:
    """Raise DomainError with the precise reason a sale is not allowed."""

    q = db.query(Provider).filter(Provider.provider_id == provider_id)
    if lock_provider:
        # Serialises capacity checks for this kitchen across concurrent orders
        q = q.with_for_update()
    provider = q.first()
    reason = provider_block_reason(provider)
    if reason:
        raise DomainError(reason)

    package = db.query(MenuPackage).filter(MenuPackage.package_id == package_id).first()
    reason = package_block_reason(package)
    if reason:
        raise DomainError(reason if package else "Package not found", 400 if package else 404)

    if offering(db, provider_id, package_id) is None:
        raise DomainError("This kitchen does not offer the selected package")

    if for_subscription and not package.is_subscription_available:
        raise DomainError(f"Package '{package.package_name}' is not available for subscription")

    if serviceable_pincode(db, provider.pincode) is None:
        raise DomainError("This kitchen's area is not currently serviced by Orleeno")

    if delivery_pincode is not None:
        pin = parse_pincode(delivery_pincode)
        if pin is None or serviceable_pincode(db, pin) is None:
            raise DomainError("Your delivery pincode is not serviceable yet", code="PINCODE_NOT_SERVICEABLE")
        if not kitchen_serves(db, provider, pin):
            raise DomainError(
                "This kitchen does not deliver to your address pincode",
                code="ADDRESS_NOT_SERVICEABLE",
            )

    return provider, package
