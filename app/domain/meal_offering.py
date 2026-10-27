"""
The meals a kitchen regularly serves, and what follows from it.

offered_slots() is the one answer to "which meals does this kitchen serve
on a day": the slots of its active, approved packages (what customers can
actually buy), or - when it has no such package - the meal service type of
its profile. It is never what happened to be ordered on a date.

A kitchen has no per-weekday meal setting, so the same standard set applies
to every weekday. Callers still pass the date, so a weekday-specific setting
would only have to be read here.

Used by emergency holidays: the meals a kitchen may block, the delivery
time that closes deletion of a full-day holiday (its earliest meal), and
free_skip_eligibility() - a full-day holiday grants a free skip only when
the kitchen normally serves at least two meals a day.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.domain.eligibility import package_sellable_filter
from app.domain.slots import SLOTS, ordered_slots, package_slots
from app.models.menu_package_model import MenuPackage
from app.models.provider_model import Provider
from app.models.provider_selected_package_model import ProviderSelectedPackage

# A full-day holiday grants the free skip only from this many meals a day
MIN_MEALS_FOR_FREE_SKIP = 2

# providers.meal_service_type (profile) -> slots
SERVICE_TYPE_SLOTS = {
    "Breakfast": ("breakfast",),
    "Lunch": ("lunch",),
    "Dinner": ("dinner",),
    "Lunch and Dinner": ("lunch", "dinner"),
    "Lunch and Breakfast": ("breakfast", "lunch"),
    "Breakfast and Dinner": ("breakfast", "dinner"),
    "Lunch and Dinner and Breakfast": SLOTS,
    "Full Day": SLOTS,
}


def offered_slots(db: Session, provider_id, on: date | None = None) -> list[str]:
    """The meals the kitchen regularly serves (on `on`: the same set every weekday), in SLOTS order."""
    rows = (
        db.query(MenuPackage.meal_type)
        .join(ProviderSelectedPackage, ProviderSelectedPackage.package_id == MenuPackage.package_id)
        .filter(
            ProviderSelectedPackage.provider_id == provider_id,
            ProviderSelectedPackage.is_active == True,  # noqa: E712
            package_sellable_filter(),
        )
        .all()
    )
    served = {slot for (meal_type,) in rows for slot in package_slots(meal_type)}
    if served:
        return ordered_slots(served)
    service = db.query(Provider.meal_service_type).filter(Provider.provider_id == provider_id).scalar()
    return list(SERVICE_TYPE_SLOTS.get(getattr(service, "value", service), ()))


@dataclass(frozen=True)
class SkipEligibility:
    eligible: bool
    slots: tuple[str, ...]
    reason: str

    def view(self) -> dict:
        return {"eligible": self.eligible, "reason": self.reason, "meals_per_day": len(self.slots)}


def free_skip_eligibility(db: Session, provider_id, on: date) -> SkipEligibility:
    """
    Whether a FULL-DAY holiday of the kitchen on `on` grants every active
    subscription its free skip: only when the kitchen normally serves at
    least MIN_MEALS_FOR_FREE_SKIP distinct meals that day.
    """
    slots = tuple(offered_slots(db, provider_id, on))
    weekday = on.strftime("%A")
    if len(slots) >= MIN_MEALS_FOR_FREE_SKIP:
        return SkipEligibility(True, slots, f"the kitchen normally serves {len(slots)} meals on {weekday}")
    served = ", ".join(slots) if slots else "no meals"
    return SkipEligibility(
        False, slots,
        f"the kitchen normally serves {len(slots)} meal(s) on {weekday} ({served}); "
        f"a free skip needs at least {MIN_MEALS_FOR_FREE_SKIP}",
    )
