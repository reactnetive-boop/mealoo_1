"""Admin: serviceable pincodes (where Orleeno operates)."""

from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import DomainError
from app.domain.eligibility import serves_pincode_filter
from app.models.provider_model import Provider
from app.models.subscription_model import Subscription
from app.models.serviceable_pincode_model import ServiceablePincode
from app.models.user_address_model import UserAddress
def _pin_view(p: ServiceablePincode) -> dict:
    return {
        "pincode_id": p.pincode_id,
        "pincode": p.pincode,
        "city": p.city,
        "state": p.state,
        "is_active": bool(p.is_active),
        "created_at": p.created_at,
    }


def _pincode_usage(db: Session, pincode: int) -> dict:
    providers = db.query(Provider).filter(serves_pincode_filter(pincode)).count()
    running_subs = (
        db.query(Subscription)
        .join(UserAddress, UserAddress.user_address_id == Subscription.user_address_reference_id)
        .filter(UserAddress.pin_code == str(pincode), Subscription.status.in_(("active", "paused")))
        .count()
    )
    return {"kitchens": providers, "running_subscriptions": running_subs}


class AdminPincodeService:

    @staticmethod
    def list_pincodes(db: Session, is_active: bool = None, city: str = None):
        query = db.query(ServiceablePincode)
        if is_active is not None:
            query = query.filter(ServiceablePincode.is_active == is_active)
        if city:
            query = query.filter(ServiceablePincode.city.ilike(f"%{city}%"))
        pincodes = query.order_by(ServiceablePincode.pincode).all()
        return {"success": True, "total": len(pincodes), "pincodes": [_pin_view(p) for p in pincodes]}

    @staticmethod
    def create_pincode(db: Session, payload, admin_id: str, ip: str | None = None):
        existing = db.query(ServiceablePincode).filter(ServiceablePincode.pincode == payload.pincode).first()
        if existing:
            raise DomainError(f"Pincode {payload.pincode} already exists", 409)
        pincode = ServiceablePincode(pincode=payload.pincode, city=payload.city, state=payload.state, is_active=True)
        db.add(pincode)
        db.flush()
        record_audit(
            db, table="master.serviceable_pincodes", operation="I", new=_pin_view(pincode),
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        db.refresh(pincode)
        return {"success": True, "message": "Pincode added", "pincode": _pin_view(pincode)}

    @staticmethod
    def update_pincode(db: Session, pincode_id: int, payload, admin_id: str, ip: str | None = None):
        pincode = db.query(ServiceablePincode).filter(ServiceablePincode.pincode_id == pincode_id).first()
        if not pincode:
            raise DomainError("Pincode not found", 404)
        before = _pin_view(pincode)
        update_data = payload.model_dump(exclude_unset=True)
        for key in ("city", "state", "is_active"):
            if key in update_data and update_data[key] is None:
                raise DomainError(f"{key} cannot be empty")
        for key, value in update_data.items():
            setattr(pincode, key, value)
        record_audit(
            db, table="master.serviceable_pincodes", old=before, new=_pin_view(pincode),
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        db.refresh(pincode)
        message = "Pincode updated"
        if before["is_active"] and not pincode.is_active:
            usage = _pincode_usage(db, pincode.pincode)
            message = (
                "Pincode deactivated: no new subscriptions or orders there. "
                f"{usage['running_subscriptions']} running subscription(s) continue."
            )
        return {"success": True, "message": message, "pincode": _pin_view(pincode)}

    @staticmethod
    def delete_pincode(db: Session, pincode_id: int, admin_id: str, ip: str | None = None):
        pincode = db.query(ServiceablePincode).filter(ServiceablePincode.pincode_id == pincode_id).first()
        if not pincode:
            raise DomainError("Pincode not found", 404)
        usage = _pincode_usage(db, pincode.pincode)
        if usage["kitchens"] or usage["running_subscriptions"]:
            raise DomainError(
                f"Pincode is in use ({usage['kitchens']} kitchen(s), {usage['running_subscriptions']} running "
                "subscription(s)). Deactivate it instead."
            )
        before = _pin_view(pincode)
        db.delete(pincode)
        record_audit(
            db, table="master.serviceable_pincodes", operation="D", old=before,
            actor_id=admin_id, actor_type="admin", ip=ip,
        )
        db.commit()
        return {"success": True, "message": "Pincode deleted"}
