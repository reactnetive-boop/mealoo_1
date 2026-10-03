from datetime import date as date_type, timedelta

from fastapi import HTTPException
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.errors import DomainError
from app.domain import capacity
from app.domain.eligibility import serviceable_pincode, parse_pincode
from app.domain.slots import SLOTS, is_before_cutoff
from app.models.delivery_boy_model import DeliveryBoy
from app.models.provider_unavailability_model import ProviderUnavailability
from app.repositories.provider_repository import ProviderRepository
from app.utils.file_helper import save_profile_image, delete_upload

# Everything a kitchen must provide before it can be reviewed
REQUIRED_PROFILE_FIELDS = (
    ("full_name", "Full name"),
    ("business_name", "Business name"),
    ("kitchen_type", "Kitchen type"),
    ("meal_service_type", "Meal service type"),
    ("daily_meal_quota", "Daily meal quota"),
    ("house_no", "House number"),
    ("address", "Address"),
    ("area", "Area"),
    ("city", "City"),
    ("state", "State"),
    ("pincode", "Pincode"),
)


def missing_profile_fields(provider) -> list[str]:
    missing = []
    for attr, label in REQUIRED_PROFILE_FIELDS:
        value = getattr(provider, attr)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(label)
    return missing


def _get(db, provider_id):
    provider = ProviderRepository.get_by_provider_id(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


def _assert_serviceable(db, pincode) -> int:
    pin = parse_pincode(pincode)
    if pin is None:
        raise DomainError("Enter a valid 6-digit pincode")
    if serviceable_pincode(db, pin) is None:
        raise DomainError(
            f"Orleeno does not operate in pincode {pin} yet. Please contact support.",
            code="PINCODE_NOT_SERVICEABLE",
        )
    return pin


class ProviderService:

    @staticmethod
    def get_state(db: Session, provider_id: str) -> dict:
        """
        Everything the kitchen app needs to pick a screen. The app must not
        decide navigation from local flags; it renders `next_step`.
        """

        provider = _get(db, provider_id)
        missing = missing_profile_fields(provider)
        profile_completed = bool(provider.is_profile_completed) and not missing

        if not profile_completed:
            next_step = "complete_profile"
        elif not provider.is_active:
            next_step = "account_inactive"
        elif provider.approval_status == "rejected":
            next_step = "approval_rejected"
        elif provider.approval_status != "approved":
            next_step = "awaiting_approval"
        else:
            next_step = "dashboard"

        return {
            "success": True,
            "provider_id": str(provider.provider_id),
            "is_authenticated": True,
            "is_mobile_verified": bool(provider.is_mobile_verified),
            "is_active": bool(provider.is_active),
            "is_profile_completed": profile_completed,
            "missing_profile_fields": missing,
            "approval_status": provider.approval_status,
            "approval_note": provider.approval_note,
            "is_accepting_orders": bool(provider.is_accepting_orders),
            "is_holiday_today": db.query(ProviderUnavailability).filter(
                ProviderUnavailability.provider_reference_id == provider.provider_id,
                ProviderUnavailability.unavailable_date == today_local(),
            ).first() is not None,
            "next_step": next_step,
        }

    @staticmethod
    def complete_profile(db, provider_id: str, payload):
        provider = _get(db, provider_id)

        update_data = payload.model_dump(exclude_unset=True)
        update_data["pincode"] = _assert_serviceable(db, update_data.get("pincode", provider.pincode))

        new_quota = update_data.get("daily_meal_quota")
        if new_quota is not None and provider.daily_meal_quota != new_quota:
            peak = capacity.peak_future_demand(db, provider.provider_id, today_local())
            if new_quota < peak:
                raise DomainError(f"Daily meal quota cannot be below {peak}, the meals already booked for a day")

        for key, value in update_data.items():
            setattr(provider, key, value)

        missing = missing_profile_fields(provider)
        if missing:
            raise DomainError("Please fill: " + ", ".join(missing), code="PROFILE_INCOMPLETE")

        provider.is_profile_completed = True
        # A rejected kitchen re-submitting goes back into the review queue
        if provider.approval_status == "rejected":
            provider.approval_status = "pending"
        db.commit()
        db.refresh(provider)

        return {
            "success": True,
            "message": "Profile completed successfully",
            "provider_id": provider.provider_id,
            "is_profile_completed": provider.is_profile_completed,
            "approval_status": provider.approval_status,
        }

    @staticmethod
    def get_profile(db, provider_id: str):
        return _get(db, provider_id)

    @staticmethod
    def update_profile_image(db: Session, provider_id: str, file: UploadFile):
        provider = _get(db, provider_id)
        old = provider.profile_image
        provider.profile_image = save_profile_image(file)
        db.commit()
        delete_upload(old)
        return {
            "success": True,
            "message": "Profile image updated successfully",
            "profile_image": provider.profile_image,
        }

    @staticmethod
    def update_daily_quota(db, provider_id: str, payload):
        provider = _get(db, provider_id)
        new_quota = payload.daily_meal_quota
        peak = capacity.peak_future_demand(db, provider.provider_id, today_local())
        if new_quota is not None and new_quota < peak:
            raise DomainError(
                f"Cannot set the daily limit to {new_quota}: {peak} meal(s) are already booked "
                f"for a single meal slot on an upcoming day. The limit must be at least {peak}."
            )
        provider.daily_meal_quota = new_quota
        db.commit()
        db.refresh(provider)
        return {
            "success": True,
            "message": (
                f"Daily limit set to {new_quota} meal(s) per slot"
                if new_quota is not None else "Daily limit removed"
            ),
            "daily_meal_quota": provider.daily_meal_quota,
            "current_peak_demand": peak,
        }

    @staticmethod
    def get_daily_quota_status(db, provider_id: str, for_date: date_type = None):
        _get(db, provider_id)
        return {"success": True, **capacity.quota_status(db, provider_id, for_date or today_local())}

    @staticmethod
    def update_address(db, provider_id: str, request):
        provider = _get(db, provider_id)
        pin = _assert_serviceable(db, request.pincode)
        provider.house_no = request.house_no
        provider.address = request.address
        provider.landmark = request.landmark
        provider.city = request.city
        provider.state = request.state
        if request.area is not None:
            provider.area = request.area
        provider.pincode = pin
        provider.is_profile_completed = not missing_profile_fields(provider)
        db.commit()
        return {"success": True, "message": "Address updated successfully"}

    @staticmethod
    def set_accepting_orders(db, provider_id: str, accepting: bool):
        provider = _get(db, provider_id)
        provider.is_accepting_orders = accepting
        db.commit()
        return {
            "success": True,
            "message": "You are accepting new orders" if accepting else "New orders are paused",
            "is_accepting_orders": provider.is_accepting_orders,
        }

    # ── Holidays (kitchen self-service) ───────────────────────

    @staticmethod
    def list_holidays(db, provider_id: str):
        rows = (
            db.query(ProviderUnavailability)
            .filter(
                ProviderUnavailability.provider_reference_id == provider_id,
                ProviderUnavailability.unavailable_date >= today_local() - timedelta(days=30),
            )
            .order_by(ProviderUnavailability.unavailable_date.asc())
            .all()
        )
        return {"success": True, "total": len(rows), "holidays": rows}

    @staticmethod
    def add_holiday(db, provider_id: str, on: date_type, reason: str | None):
        if on < today_local() or (on == today_local() and not all(is_before_cutoff(on, s) for s in SLOTS)):
            raise DomainError("A holiday must be marked before that day's first meal cut-off")
        exists = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == provider_id,
            ProviderUnavailability.unavailable_date == on,
        ).first()
        if exists:
            raise DomainError(f"{on} is already marked as a holiday", 409)
        record = ProviderUnavailability(provider_reference_id=provider_id, unavailable_date=on, reason=reason)
        db.add(record)
        db.commit()
        db.refresh(record)
        return {
            "success": True,
            "message": (
                f"Holiday marked for {on}. Orleeno may move that day's orders to another kitchen; "
                "orders that cannot be moved are cancelled and refunded at the cut-off."
            ),
            "holiday": record,
        }

    @staticmethod
    def remove_holiday(db, provider_id: str, on: date_type):
        record = db.query(ProviderUnavailability).filter(
            ProviderUnavailability.provider_reference_id == provider_id,
            ProviderUnavailability.unavailable_date == on,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Holiday not found")
        if on < today_local():
            raise DomainError("Past holidays cannot be removed")
        db.delete(record)
        db.commit()
        return {"success": True, "message": f"Holiday on {on} removed"}

    # ── Delivery partners this kitchen may assign ─────────────

    @staticmethod
    def assignable_delivery_partners(db, provider_id: str):
        boys = (
            db.query(DeliveryBoy)
            .filter(
                DeliveryBoy.is_active == True,  # noqa: E712
                DeliveryBoy.approval_status == "approved",
                (DeliveryBoy.assigned_provider_reference_id == provider_id)
                | (DeliveryBoy.assigned_provider_reference_id.is_(None)),
            )
            .order_by(DeliveryBoy.is_online.desc(), DeliveryBoy.full_name.asc())
            .all()
        )
        return {
            "success": True,
            "total": len(boys),
            "delivery_partners": [
                {
                    "delivery_boy_id": b.delivery_boy_id,
                    "full_name": b.full_name,
                    "mobile_number": b.mobile_number,
                    "vehicle_type": b.vehicle_type,
                    "vehicle_number": b.vehicle_number,
                    "is_online": b.is_online,
                    "is_dedicated": b.assigned_provider_reference_id is not None,
                }
                for b in boys
            ],
        }
