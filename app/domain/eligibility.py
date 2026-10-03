"""
Who can sell what to whom.

A package is sellable to a customer only when ALL of these hold:
  kitchen active + approved + profile complete + accepting orders
  package approved + active + available + not deleted
  the kitchen offers the package (own package, or a catalogue package it
    selected)
  the kitchen's pincode is an active serviceable pincode and equals the
    customer's delivery pincode
  (subscriptions) the package allows subscription
  (a given date) the kitchen is not on holiday that day

Listing, cart, subscription, extra order and switch all call these
functions, so the rules cannot drift between screens.
"""

from datetime import date

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage
from app.models.provider_unavailability_model import ProviderUnavailability
from app.models.serviceable_pincode_model import ServiceablePincode


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
        if pin != provider.pincode:
            raise DomainError(
                "This kitchen does not deliver to your address pincode",
                code="ADDRESS_NOT_SERVICEABLE",
            )

    return provider, package
