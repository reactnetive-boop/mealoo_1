"""
Explicit admin-facing serialisers.

Admin endpoints used to return ORM objects directly, which serialised every
column, including password hashes and customer delivery codes. Every admin
response now goes through one of these allow-listed views.
"""

from app.domain.pricing import package_price_view
from app.core.config import DELIVERY_CODE_MAX_ATTEMPTS, PICKUP_CODE_MAX_ATTEMPTS


def mask(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return value
    value = str(value)
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


def provider_view(p) -> dict:
    return {
        "provider_id": p.provider_id,
        "full_name": p.full_name,
        "business_name": p.business_name,
        "mobile_number": p.mobile_number,
        "kitchen_type": p.kitchen_type,
        "meal_service_type": p.meal_service_type,
        "fssai_licence": p.fssai_licence,
        "house_no": p.house_no,
        "address": p.address,
        "area": p.area,
        "landmark": p.landmark,
        "city": p.city,
        "state": p.state,
        "pincode": p.pincode,
        "profile_image": p.profile_image,
        "daily_meal_quota": p.daily_meal_quota,
        "is_mobile_verified": bool(p.is_mobile_verified),
        "is_profile_completed": bool(p.is_profile_completed),
        "is_active": bool(p.is_active),
        "is_accepting_orders": bool(p.is_accepting_orders),
        "approval_status": p.approval_status,
        "approval_note": p.approval_note,
        "approved_at": p.approved_at,
        "is_locked": bool(p.locked_until),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def delivery_boy_view(b) -> dict:
    return {
        "delivery_boy_id": b.delivery_boy_id,
        "full_name": b.full_name,
        "mobile_number": b.mobile_number,
        "email": b.email,
        "date_of_birth": b.date_of_birth,
        "gender": b.gender,
        "vehicle_type": b.vehicle_type,
        "vehicle_number": b.vehicle_number,
        "profile_image": b.profile_image,
        "assigned_provider_reference_id": b.assigned_provider_reference_id,
        "is_mobile_verified": bool(b.is_mobile_verified),
        "is_active": bool(b.is_active),
        "is_online": bool(b.is_online),
        "approval_status": b.approval_status,
        "approval_note": b.approval_note,
        "approved_at": b.approved_at,
        "created_at": b.created_at,
        "updated_at": b.updated_at,
    }


def user_view(u) -> dict:
    return {
        "user_id": u.user_id,
        "full_name": u.full_name,
        "phone": u.phone,
        "email": u.email,
        "gender": u.gender,
        "date_of_birth": u.date_of_birth,
        "avatar_url": u.avatar_url,
        "phone_verified": bool(u.phone_verified),
        "email_verified": bool(u.email_verified),
        "is_profile_completed": bool(u.is_profile_completed),
        "status": u.status,
        "last_login_at": u.last_login_at,
        "created_at": u.created_at,
    }


def address_view(a) -> dict:
    return {
        "user_address_id": a.user_address_id,
        "label": a.label,
        "address_line1": a.address_line1,
        "address_line2": a.address_line2,
        "landmark": a.landmark,
        "city": a.city,
        "state": a.state,
        "pin_code": a.pin_code,
        "country": a.country,
        "is_default": bool(a.is_default),
        "is_active": bool(a.is_active),
    }


def subscription_admin_view(s) -> dict:
    return {
        "subscription_id": s.subscription_id,
        "user_reference_id": s.user_reference_id,
        "vendor_reference_id": s.vendor_reference_id,
        "plan_reference_id": s.plan_reference_id,
        "user_address_reference_id": s.user_address_reference_id,
        "status": s.status,
        "meal_slot": s.meal_slot,
        "subscription_type": s.subscription_type,
        "start_date": s.start_date,
        "end_date": s.end_date,
        "free_skips_total": s.free_skips_total,
        "free_skips_used": s.free_skips_used,
        "total_amount": s.total_amount,
        "discount_amount": s.discount_amount,
        "charges_amount": s.charges_amount,
        "final_amount": s.final_amount,
        "refunded_amount": s.refunded_amount,
        "pricing_snapshot": s.pricing_snapshot,
        "pause_start_date": s.pause_start_date,
        "total_days_paused": s.total_days_paused,
        "delivery_boy_reference_id": s.delivery_boy_reference_id,
        "cancelled_at": s.cancelled_at,
        "cancel_reason": s.cancel_reason,
        "created_at": s.created_at,
    }


def _order_common(o) -> dict:
    # Customer delivery codes and kitchen pickup codes are never shown to admins
    return {
        "user_reference_id": o.user_reference_id,
        "vendor_reference_id": o.vendor_reference_id,
        "meal_slot": o.meal_slot,
        "status": o.status,
        "delivery_boy_reference_id": o.delivery_boy_reference_id,
        "delivered_at": o.delivered_at,
        "picked_up_at": o.picked_up_at,
        "out_for_delivery_at": o.out_for_delivery_at,
        "arrived_at": o.arrived_at,
        "delivery_code_attempts": o.delivery_code_attempts or 0,
        "pickup_code_attempts": o.pickup_code_attempts or 0,
        # locked by wrong codes: needs Orleeno to step in (thresholds live on the server)
        "pickup_locked": (o.pickup_code_attempts or 0) >= PICKUP_CODE_MAX_ATTEMPTS,
        "delivery_locked": (o.delivery_code_attempts or 0) >= DELIVERY_CODE_MAX_ATTEMPTS,
        "failed_at": o.failed_at,
        "failure_reason": o.failure_reason,
        "cancel_reason": o.cancel_reason,
        "refund_amount": o.refund_amount,
        "refunded_at": o.refunded_at,
        "settled_at": o.settled_at,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }


def order_admin_view(o) -> dict:
    return {
        "order_id": o.order_id,
        "subscription_reference_id": o.subscription_reference_id,
        "delivery_address_reference_id": o.delivery_address_reference_id,
        "order_date": o.order_date,
        "is_free_skip": bool(o.is_free_skip),
        "skip_requested_at": o.skip_requested_at,
        "skip_deadline": o.skip_deadline,
        "delivery_notes": o.delivery_notes,
        **_order_common(o),
    }


def extra_order_admin_view(o) -> dict:
    return {
        "extra_order_id": o.extra_order_id,
        "checkout_id": o.checkout_id,
        "package_reference_id": o.package_reference_id,
        "address_reference_id": o.address_reference_id,
        "quantity": o.quantity,
        "unit_price": o.unit_price,
        "total_price": o.total_price,
        "charges_amount": o.charges_amount,
        "pricing_snapshot": o.pricing_snapshot,
        "delivery_date": o.delivery_date,
        **_order_common(o),
    }


def package_admin_view(pkg, provider_name: str | None = None) -> dict:
    data = {
        "package_id": pkg.package_id,
        # catalogue packages belong to Orleeno: never expose the creating admin's id
        "provider_id": None if pkg.is_predefined else pkg.provider_id,
        "provider_reference_id": None if pkg.is_predefined else pkg.provider_id,
        "provider_name": provider_name,
        "category_reference_id": pkg.category_reference_id,
        "package_name": pkg.package_name,
        "short_description": pkg.short_description,
        "description": pkg.description,
        "meal_type": pkg.meal_type,
        "food_type": pkg.food_type,
        "price": pkg.price,
        "discounted_price": pkg.discounted_price,
        "subscription_price": pkg.subscription_price,
        "is_subscription_available": bool(pkg.is_subscription_available),
        "is_active": bool(pkg.is_active),
        "is_available": bool(pkg.is_available),
        "is_predefined": bool(pkg.is_predefined),
        "approval_status": pkg.approval_status,
        "approval_note": pkg.approval_note,
        "pending_changes": pkg.pending_changes,
        "pending_changes_at": pkg.pending_changes_at,
        "approved_at": pkg.approved_at,
        "deleted_at": pkg.deleted_at,
        "created_at": pkg.created_at,
        "updated_at": pkg.updated_at,
    }
    data.update(package_price_view(pkg))
    return data


def payout_details_view(p, reveal: bool = False) -> dict | None:
    if p is None:
        return None
    return {
        "account_holder_name": p.account_holder_name,
        "account_number": p.account_number if reveal else mask(p.account_number),
        "ifsc_code": p.ifsc_code,
        "bank_name": p.bank_name,
        "upi_id": p.upi_id,
        "updated_at": p.updated_at,
    }
