from fastapi import APIRouter

from app.core.clock import today_local, now_local
from app.core.config import (
    BUSINESS_TIMEZONE,
    EXTRA_ORDER_MAX_DAYS_AHEAD,
    SUBSCRIPTION_MAX_START_DAYS_AHEAD,
    CUSTOM_PLAN_MIN_DAYS,
    CUSTOM_PLAN_MAX_DAYS,
)
from app.domain.slots import cutoffs_public, windows_public, SLOTS

router = APIRouter()


@router.get(
    "/config",
    summary="Business Rules the Apps Display",
    description=(
        "Business timezone, today's business date, the same-day meal cut-offs and the delivery "
        "time windows. Apps use "
        "these to label choices; the server enforces them on every request."
    ),
)
def public_config():
    return {
        "success": True,
        "timezone": BUSINESS_TIMEZONE,
        "business_date": today_local(),
        "server_time": now_local(),
        "meal_slots": list(SLOTS),
        "meal_cutoffs": cutoffs_public(),
        # when each meal is promised at the door
        "delivery_windows": windows_public(),
        "extra_order_max_days_ahead": EXTRA_ORDER_MAX_DAYS_AHEAD,
        "subscription_max_start_days_ahead": SUBSCRIPTION_MAX_START_DAYS_AHEAD,
        "custom_plan_min_days": CUSTOM_PLAN_MIN_DAYS,
        "custom_plan_max_days": CUSTOM_PLAN_MAX_DAYS,
        "payment_mode": "internal_wallet",
    }
