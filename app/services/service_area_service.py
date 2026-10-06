"""
Kitchen service areas: extra pincodes a kitchen delivers to besides its own.

Orleeno (admin) decides them, because delivery distance and partner coverage
are operational decisions. A pincode can be added only when Orleeno serves it,
and removed only when no running subscription or open one-time order of the
kitchen is delivered there.
"""

from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import DomainError
from app.domain import notify
from app.domain.eligibility import serviceable_pincode
from app.domain.status import EXTRA_OPEN_STATUSES
from app.models.extra_order_model import ExtraOrder
from app.models.provider_model import Provider
from app.models.provider_service_area_model import ProviderServiceArea
from app.models.subscription_model import Subscription
from app.models.user_address_model import UserAddress


def _kitchen(db: Session, provider_id) -> Provider:
    provider = db.query(Provider).filter(Provider.provider_id == provider_id).first()
    if provider is None:
        raise DomainError("Provider not found", 404)
    return provider


def _view(provider: Provider, areas) -> dict:
    return {
        "success": True,
        "provider_id": provider.provider_id,
        "home_pincode": provider.pincode,
        "service_areas": [
            {"pincode": a.pincode, "created_at": a.created_at} for a in sorted(areas, key=lambda a: a.pincode)
        ],
        "all_pincodes": sorted({provider.pincode, *(a.pincode for a in areas)} - {None}),
    }


def _areas(db: Session, provider_id):
    return db.query(ProviderServiceArea).filter(ProviderServiceArea.provider_reference_id == provider_id).all()


def _open_deliveries_to(db: Session, provider_id, pincode: int) -> int:
    subs = (
        db.query(Subscription)
        .join(UserAddress, UserAddress.user_address_id == Subscription.user_address_reference_id)
        .filter(
            Subscription.vendor_reference_id == provider_id,
            Subscription.status.in_(("active", "paused")),
            UserAddress.pin_code == str(pincode),
        )
        .count()
    )
    one_time = (
        db.query(ExtraOrder)
        .join(UserAddress, UserAddress.user_address_id == ExtraOrder.address_reference_id)
        .filter(
            ExtraOrder.vendor_reference_id == provider_id,
            ExtraOrder.status.in_(EXTRA_OPEN_STATUSES),
            UserAddress.pin_code == str(pincode),
        )
        .count()
    )
    return subs + one_time


class ServiceAreaService:

    @staticmethod
    def list(db: Session, provider_id) -> dict:
        provider = _kitchen(db, provider_id)
        return _view(provider, _areas(db, provider_id))

    @staticmethod
    def add(db: Session, provider_id, pincode: int, admin_id: str, ip: str | None = None) -> dict:
        provider = _kitchen(db, provider_id)
        if pincode == provider.pincode:
            raise DomainError("That is the kitchen's own pincode; it is always served")
        if serviceable_pincode(db, pincode) is None:
            raise DomainError(f"Orleeno does not serve {pincode} yet. Add it as a serviceable pincode first.")
        exists = db.query(ProviderServiceArea).filter(
            ProviderServiceArea.provider_reference_id == provider_id, ProviderServiceArea.pincode == pincode
        ).first()
        if exists:
            raise DomainError(f"The kitchen already delivers to {pincode}", 409)

        db.add(ProviderServiceArea(provider_reference_id=provider.provider_id, pincode=pincode, created_by=admin_id))
        record_audit(
            db, table="provider.provider_service_areas", record_id=provider.provider_id, operation="I",
            new={"pincode": pincode}, actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.kitchen(
            db, provider.provider_id, "account_update", "New delivery area",
            f"Customers in {pincode} can now order from your kitchen.", {"pincode": pincode},
        )
        db.commit()
        return _view(provider, _areas(db, provider_id))

    @staticmethod
    def remove(db: Session, provider_id, pincode: int, admin_id: str, ip: str | None = None) -> dict:
        provider = _kitchen(db, provider_id)
        area = db.query(ProviderServiceArea).filter(
            ProviderServiceArea.provider_reference_id == provider_id, ProviderServiceArea.pincode == pincode
        ).with_for_update().first()
        if area is None:
            raise DomainError(f"The kitchen does not have {pincode} as a delivery area", 404)
        running = _open_deliveries_to(db, provider_id, pincode)
        if running:
            raise DomainError(
                f"{running} running subscription(s) or open order(s) are delivered to {pincode}. "
                "Move or finish them before removing the area.",
                409,
                code="AREA_IN_USE",
            )
        db.delete(area)
        record_audit(
            db, table="provider.provider_service_areas", record_id=provider.provider_id, operation="D",
            old={"pincode": pincode}, actor_id=admin_id, actor_type="admin", ip=ip,
        )
        notify.kitchen(
            db, provider.provider_id, "account_update", "Delivery area removed",
            f"Your kitchen no longer takes new orders from {pincode}.", {"pincode": pincode},
        )
        db.commit()
        return _view(provider, _areas(db, provider_id))
