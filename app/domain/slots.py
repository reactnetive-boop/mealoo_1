"""
Meal slots, plan slot combinations and same-day cut-offs.

This module is the only place cut-off times are defined. Customer ordering,
subscription start, skips, cancellations and admin re-assignment all read
them from here, and the apps read them through GET /api/v1/public/config.
"""

from datetime import date, time, timedelta

from app.core.clock import now_local, today_local, local_datetime
from app.utils.meal_type import meal_type_to_list

SLOTS = ("breakfast", "lunch", "dinner")

# Plan meal_slot value -> individual daily meals
PLAN_SLOT_EXPANSION: dict[str, list[str]] = {
    "breakfast": ["breakfast"],
    "lunch": ["lunch"],
    "dinner": ["dinner"],
    "breakfast_lunch": ["breakfast", "lunch"],
    "lunch_dinner": ["lunch", "dinner"],
    "breakfast_dinner": ["breakfast", "dinner"],
    "all_slots": ["breakfast", "lunch", "dinner"],
}

PLAN_SLOT_VALUES = tuple(PLAN_SLOT_EXPANSION.keys())

# Aliases admins / older data used for "all three"
_PLAN_SLOT_ALIASES = {
    "all": "all_slots",
    "all_day": "all_slots",
    "full_day": "all_slots",
    "lunch_breakfast": "breakfast_lunch",
    "dinner_lunch": "lunch_dinner",
    "dinner_breakfast": "breakfast_dinner",
}

# Last moment (business-local) to order, skip or cancel a meal for the same
# day. After it the kitchen is cooking.
SLOT_CUTOFFS: dict[str, time] = {
    "breakfast": time(6, 0),
    "lunch": time(9, 0),
    "dinner": time(15, 0),
}


# When each meal is promised at the door (business-local). Shown to customers
# and partners; a meal delivered after the window's end counts as late.
SLOT_WINDOWS: dict[str, tuple[time, time]] = {
    "breakfast": (time(7, 0), time(9, 30)),
    "lunch": (time(12, 0), time(14, 30)),
    "dinner": (time(19, 0), time(21, 30)),
}


def delivery_window(slot: str) -> dict | None:
    window = SLOT_WINDOWS.get(slot)
    if window is None:
        return None
    return {"from": window[0].strftime("%H:%M"), "to": window[1].strftime("%H:%M")}


def window_end(day: date, slot: str):
    """Business-local moment a meal of `slot` on `day` becomes late."""
    return local_datetime(day, SLOT_WINDOWS[slot][1])


def normalize_plan_slot(value: str) -> str:
    v = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    v = _PLAN_SLOT_ALIASES.get(v, v)
    if v not in PLAN_SLOT_EXPANSION:
        raise ValueError(
            f"Invalid meal slot '{value}'. Allowed: {', '.join(PLAN_SLOT_VALUES)}"
        )
    return v


def expand_plan_slot(plan_slot: str) -> list[str]:
    """Individual meals per day for a plan slot; unknown values -> []."""
    try:
        return list(PLAN_SLOT_EXPANSION[normalize_plan_slot(plan_slot)])
    except ValueError:
        return []


def package_slots(meal_type: str | None) -> list[str]:
    """Slots a package is served in, from its canonical meal_type string."""
    return [s for s in meal_type_to_list(meal_type) if s in SLOTS]


def package_serves(meal_type: str | None, slots: list[str]) -> bool:
    served = set(package_slots(meal_type))
    return bool(slots) and all(s in served for s in slots)


def cutoff_at(on: date, slot: str):
    return local_datetime(on, SLOT_CUTOFFS[slot])


def is_before_cutoff(on: date, slot: str) -> bool:
    """True when the same-day window for this meal is still open."""
    if on > today_local():
        return True
    if on < today_local():
        return False
    return now_local() < cutoff_at(on, slot)


def earliest_service_date(slots: list[str]) -> date:
    """
    First date on which every given slot can still be served.

    Today counts only if it is before the cut-off of the earliest slot
    involved; otherwise service starts tomorrow.
    """
    today = today_local()
    if slots and all(is_before_cutoff(today, s) for s in slots):
        return today
    return today + timedelta(days=1)


def cutoffs_public() -> dict:
    return {slot: SLOT_CUTOFFS[slot].strftime("%H:%M") for slot in SLOTS}


def windows_public() -> dict:
    return {slot: delivery_window(slot) for slot in SLOTS}
