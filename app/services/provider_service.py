from datetime import date as date_type

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.errors import DomainError
from app.domain import capacity, holidays, vendor_partner
from app.domain.eligibility import assert_pincode_can_change, serviceable_pincode, parse_pincode
from app.domain.slots import ordered_slots
from app.models.delivery_boy_model import DeliveryBoy
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
        raise DomainError("Provider not found", 404)
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
            "is_holiday_today": holidays.is_closed(db, provider.provider_id, today_local()),
            # meals an emergency holiday blocks today (all three when closed for the day)
            "holiday_today_meal_slots": ordered_slots(
                holidays.blocked_slots(db, provider.provider_id, today_local(), today_local()).get(today_local(), {})
            ),
            "next_step": next_step,
        }

    @staticmethod
    def complete_profile(db, provider_id: str, payload):
        provider = _get(db, provider_id)

        update_data = payload.model_dump(exclude_unset=True)
        update_data["pincode"] = _assert_serviceable(db, update_data.get("pincode", provider.pincode))
        assert_pincode_can_change(db, provider, update_data["pincode"])

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
        assert_pincode_can_change(db, provider, pin)
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

    # ── Delivery partners this kitchen may assign ─────────────

    @staticmethod
    def assignable_delivery_partners(db, provider_id: str):
        """Partners the kitchen may give an unassigned order to: its own partner, and shared-pool partners."""
        boys = (
            db.query(DeliveryBoy)
            .filter(
                DeliveryBoy.is_active == True,  # noqa: E712
                DeliveryBoy.approval_status == "approved",
            )
            .order_by(DeliveryBoy.is_online.desc(), DeliveryBoy.full_name.asc())
            .all()
        )
        kitchens = vendor_partner.kitchens_by_partner(db, (b.delivery_boy_id for b in boys))
        own = vendor_partner.kitchen_row(db, provider_id)
        rows = []
        for b in boys:
            mine = {str(p.provider_id) for _, p in kitchens.get(b.delivery_boy_id, [])}
            if mine and str(provider_id) not in mine:
                continue  # serves other kitchens only
            rows.append({
                "delivery_boy_id": b.delivery_boy_id,
                "full_name": b.full_name,
                "mobile_number": b.mobile_number,
                "vehicle_type": b.vehicle_type,
                "vehicle_number": b.vehicle_number,
                "is_online": b.is_online,
                "is_dedicated": bool(mine),
                "is_kitchen_partner": own is not None and str(own.delivery_boy_reference_id) == str(b.delivery_boy_id),
            })
        rows.sort(key=lambda r: not r["is_kitchen_partner"])
        return {"success": True, "total": len(rows), "delivery_partners": rows}

    @staticmethod
    def kitchen_delivery_partner(db, provider_id: str):
        """The partner Orleeno assigned to this kitchen; its orders and subscription meals go to them."""
        row = vendor_partner.kitchen_row(db, provider_id)
        boy = (
            db.query(DeliveryBoy).filter(DeliveryBoy.delivery_boy_id == row.delivery_boy_reference_id).first()
            if row else None
        )
        if boy is None:
            return {
                "success": True,
                "delivery_partner": None,
                "message": "No delivery partner is assigned to your kitchen yet. Orleeno will assign one.",
            }
        return {
            "success": True,
            "delivery_partner": {
                "delivery_boy_id": boy.delivery_boy_id,
                "full_name": boy.full_name,
                "mobile_number": boy.mobile_number,
                "vehicle_type": boy.vehicle_type,
                "vehicle_number": boy.vehicle_number,
                "is_online": bool(boy.is_online),
                "can_take_orders": vendor_partner.usable(boy),
                "assigned_at": row.assigned_at,
            },
            "message": None if vendor_partner.usable(boy) else
            "Your delivery partner is not active right now; new orders wait until Orleeno assigns cover.",
        }
