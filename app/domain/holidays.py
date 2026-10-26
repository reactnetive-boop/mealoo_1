"""
Kitchen holidays: rules, the kitchen calendar and subscription schedules.

Two kinds (provider.vendor_holidays):

  casual     planned in advance, from tomorrow on: every Sunday, Saturday and
             Sunday, selected weekdays, specific dates, a date range
             (vacation) or selected days of the month. A casual holiday is
             built into every price and schedule: a subscription never has a
             meal - and never pays for one - on a casual holiday.
  emergency  the kitchen suddenly cannot cook on one date (today or later).
             Meals already sold for that date go to a replacement kitchen or
             are compensated, one by one (app/domain/emergency_holiday.py);
             the subscription itself is not re-priced.

Every date is a business-local date (BUSINESS_TIMEZONE, Asia/Kolkata by
default; app.core.clock), so a holiday declared near midnight lands on the
date the kitchen sees on its calendar.

Rules are evaluated on the fly (no materialised calendar), so a weekly rule
has no horizon. Overlapping rules simply give the same closed date once: a
date is either a kitchen closure or not, and everything that reacts to a
closure (subscription re-planning, meal generation) works per (subscription,
date) and skips dates it already handled, so overlaps never double-process.

Subscription policy (no earlier policy existed; this is the default the
business asked for): the customer pays for exactly the meals they will
receive. A fixed-length plan keeps its number of meal days and its end date
moves past the kitchen's holidays; a custom plan (customer-chosen dates) is
charged only for the days the kitchen is open. The holiday dates inside a
subscription's span are stored on it (subscriptions.holiday_dates) and shown
in its price breakup and calendar.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.errors import DomainError
from app.models.vendor_holiday_model import VendorHoliday

CASUAL = "casual"
EMERGENCY = "emergency"
RULE_TYPES = ("weekly", "dates", "range", "monthly")

WEEKDAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}

PRESETS = {
    "every_sunday": {"rule_type": "weekly", "weekdays": [7]},
    "weekends": {"rule_type": "weekly", "weekdays": [6, 7]},
}

MAX_SPECIFIC_DATES = 60
MAX_RANGE_DAYS = 120
# How far a schedule may stretch past the meal days it needs before the
# kitchen is considered to have no delivery days at all
SCHEDULE_SLACK_DAYS = 400

# Labels used on every screen
CASUAL_LABEL = "Vendor holiday – no delivery"
EMERGENCY_LABEL = "Vendor emergency holiday"
NOT_CHARGED_LABEL = "Vendor holiday – not charged"


# ── Rule evaluation ───────────────────────────────────────────

def _days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def rule_dates(h: VendorHoliday, start: date, end: date) -> set[date]:
    """The closed dates of one holiday row inside [start, end] (inclusive)."""
    lo = max(start, h.start_date)
    hi = end if h.end_date is None else min(end, h.end_date)
    if lo > hi:
        return set()
    if h.rule_type == "dates":
        return {d for d in (h.dates or []) if lo <= d <= hi}
    if h.rule_type == "range":
        return set(_days(lo, hi))
    if h.rule_type == "weekly":
        wanted = set(h.weekdays or [])
        return {d for d in _days(lo, hi) if d.isoweekday() in wanted}
    if h.rule_type == "monthly":
        wanted = set(h.month_days or [])
        return {d for d in _days(lo, hi) if d.day in wanted}
    return set()


def _uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _ids(provider_ids) -> list[uuid.UUID]:
    return list({_uuid(p) for p in provider_ids if p is not None})


def _rows(db: Session, provider_ids, start: date, end: date, types=None) -> list[VendorHoliday]:
    ids = _ids(provider_ids)
    if not ids:
        return []
    q = db.query(VendorHoliday).filter(
        VendorHoliday.provider_reference_id.in_(ids),
        VendorHoliday.status == "active",
        VendorHoliday.start_date <= end,
        or_(VendorHoliday.end_date.is_(None), VendorHoliday.end_date >= start),
    )
    if types:
        q = q.filter(VendorHoliday.holiday_type.in_(tuple(types)))
    return q.order_by(VendorHoliday.created_at).all()


def closures(db: Session, provider_ids, start: date, end: date, types=None) -> dict:
    """
    {provider_id (UUID): {date: VendorHoliday}} for every closed date in [start, end].
    When a casual rule and an emergency fall on the same date the emergency is
    reported (it is the one with consequences for meals).
    """
    out: dict = defaultdict(dict)
    for h in _rows(db, provider_ids, start, end, types):
        for d in rule_dates(h, start, end):
            current = out[h.provider_reference_id].get(d)
            if current is None or (h.holiday_type == EMERGENCY and current.holiday_type != EMERGENCY):
                out[h.provider_reference_id][d] = h
    return out


def closed_dates(db: Session, provider_id, start: date, end: date, types=None) -> set[date]:
    return set(closures(db, [provider_id], start, end, types).get(_uuid(provider_id), {}))


def is_closed(db: Session, provider_id, on: date, types=None) -> bool:
    return bool(closed_dates(db, provider_id, on, on, types))


def closed_kitchens(db: Session, provider_ids, on: date, types=None) -> set:
    """The subset of `provider_ids` closed on `on` (one query for a whole list), as given."""
    given = {_uuid(p): p for p in (provider_ids or []) if p is not None}
    return {given[pid] for pid, days in closures(db, list(given), on, on, types).items() if days}


def holiday_on(db: Session, provider_id, on: date) -> VendorHoliday | None:
    return closures(db, [provider_id], on, on).get(_uuid(provider_id), {}).get(on)


# ── Subscription schedules ────────────────────────────────────

@dataclass
class Schedule:
    """Meal days of a subscription and the kitchen holidays inside its span."""

    start: date
    end: date  # exclusive
    meal_dates: list = field(default_factory=list)
    holiday_dates: list = field(default_factory=list)

    @property
    def meal_days(self) -> int:
        return len(self.meal_dates)


def plan_days(db: Session, provider_id, start: date, meal_days: int, skip=()) -> Schedule:
    """
    The first `meal_days` dates from `start` on which the kitchen is open
    (fixed-length plans): holidays are skipped and the end date moves past
    them, so the customer gets every meal day they pay for. `skip`: extra
    dates to treat as closed (already-known holidays of the subscription).
    """
    if meal_days < 1:
        raise DomainError("A plan needs at least one meal day")
    horizon = start + timedelta(days=meal_days + SCHEDULE_SLACK_DAYS)
    closed = closed_dates(db, provider_id, start, horizon) | set(skip)
    schedule = Schedule(start=start, end=start)
    current = start
    while len(schedule.meal_dates) < meal_days:
        if current > horizon:
            raise DomainError(
                "This kitchen has no delivery days in the coming months. Please choose another kitchen.",
                code="KITCHEN_NO_DELIVERY_DAYS",
            )
        if current in closed:
            schedule.holiday_dates.append(current)
        else:
            schedule.meal_dates.append(current)
        current += timedelta(days=1)
    schedule.end = current
    return schedule


def plan_range(db: Session, provider_id, start: date, last_day: date) -> Schedule:
    """Open days in [start, last_day] (custom plans: the customer chose the dates)."""
    closed = closed_dates(db, provider_id, start, last_day)
    schedule = Schedule(start=start, end=last_day + timedelta(days=1))
    for d in _days(start, last_day):
        (schedule.holiday_dates if d in closed else schedule.meal_dates).append(d)
    if not schedule.meal_dates:
        raise DomainError("The kitchen is closed on every day you chose. Please pick other dates.",
                          code="KITCHEN_CLOSED_ALL_DAYS")
    return schedule


def extend(db: Session, provider_id, end: date, meal_days: int, skip=()) -> Schedule:
    """`meal_days` more open days after an exclusive end date (pause, holiday make-up)."""
    return plan_days(db, provider_id, end, meal_days, skip)


# ── Dates stored on a subscription ────────────────────────────

def sub_holidays(sub) -> set[date]:
    return {date.fromisoformat(d) for d in (getattr(sub, "holiday_dates", None) or [])}


def set_sub_holidays(sub, dates) -> None:
    sub.holiday_dates = sorted({d.isoformat() if isinstance(d, date) else str(d) for d in dates}) or None


def add_sub_holidays(sub, dates) -> None:
    set_sub_holidays(sub, sub_holidays(sub) | set(dates))


# ── Rules from requests ───────────────────────────────────────

def _int_list(values, lo: int, hi: int, label: str) -> list[int]:
    out = sorted({int(v) for v in (values or [])})
    if not out:
        raise DomainError(f"Choose at least one {label}")
    if out[0] < lo or out[-1] > hi:
        raise DomainError(f"{label.capitalize()} must be between {lo} and {hi}")
    return out


def normalize_rule(payload: dict, *, first_day: date | None = None) -> dict:
    """
    Validated fields of a casual holiday rule (raises DomainError). Dates are
    business-local; nothing on or before today can be planned (a same-day
    closure is an emergency holiday).
    """
    data = dict(payload)
    preset = data.pop("preset", None)
    if preset:
        if preset not in PRESETS:
            raise DomainError(f"Unknown holiday option '{preset}'")
        data = {**data, **PRESETS[preset]}
    rule_type = data.get("rule_type")
    if rule_type not in RULE_TYPES:
        raise DomainError(f"rule_type must be one of: {', '.join(RULE_TYPES)}")
    first_day = first_day or (today_local() + timedelta(days=1))
    start = data.get("start_date")
    end = data.get("end_date")
    out = {"rule_type": rule_type, "weekdays": None, "month_days": None, "dates": None, "end_date": end}

    if rule_type == "dates":
        dates = sorted({d for d in (data.get("dates") or []) if d is not None})
        if data.get("date") and data["date"] not in dates:
            dates = sorted(set(dates) | {data["date"]})
        if not dates:
            raise DomainError("Choose at least one date")
        if len(dates) > MAX_SPECIFIC_DATES:
            raise DomainError(f"Choose at most {MAX_SPECIFIC_DATES} dates at a time")
        if dates[0] < first_day:
            raise DomainError("Holidays can only be planned from tomorrow. For today, declare an emergency holiday.",
                              code="HOLIDAY_IN_PAST")
        out.update(dates=dates, start_date=dates[0], end_date=dates[-1])
        return out

    start = start or first_day
    if start < first_day:
        raise DomainError("Holidays can only be planned from tomorrow. For today, declare an emergency holiday.",
                          code="HOLIDAY_IN_PAST")
    if end is not None and end < start:
        raise DomainError("The end date is before the start date")
    out["start_date"] = start

    if rule_type == "range":
        if end is None:
            raise DomainError("Choose the last day of the holiday")
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            raise DomainError(f"A holiday period can be at most {MAX_RANGE_DAYS} days")
    elif rule_type == "weekly":
        out["weekdays"] = _int_list(data.get("weekdays"), 1, 7, "weekday")
        if len(out["weekdays"]) == 7:
            raise DomainError("A kitchen cannot be closed on every day of the week")
    else:
        out["month_days"] = _int_list(data.get("month_days"), 1, 31, "day of the month")
    return out


def same_rule(h: VendorHoliday, rule: dict) -> bool:
    return (
        h.rule_type == rule["rule_type"]
        and sorted(h.weekdays or []) == sorted(rule.get("weekdays") or [])
        and sorted(h.month_days or []) == sorted(rule.get("month_days") or [])
        and sorted(h.dates or []) == sorted(rule.get("dates") or [])
        and h.start_date == rule["start_date"]
        and h.end_date == rule.get("end_date")
    )


# ── Labels ────────────────────────────────────────────────────

def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


def describe(h: VendorHoliday) -> str:
    """'Closed every Sunday', 'Closed 20 Oct 2026 - 25 Oct 2026', ..."""
    if h.holiday_type == EMERGENCY:
        return f"Emergency closure on {_fmt(h.start_date)}"
    if h.rule_type == "weekly":
        days = [WEEKDAY_NAMES[d] for d in sorted(h.weekdays or [])]
        text = f"Closed every {_join(days)}"
    elif h.rule_type == "monthly":
        text = f"Closed on the {_join([_ordinal(d) for d in sorted(h.month_days or [])])} of every month"
    elif h.rule_type == "range":
        return f"Closed {_fmt(h.start_date)} – {_fmt(h.end_date)}"
    else:
        dates = sorted(h.dates or [])
        return "Closed on " + _join([_fmt(d) for d in dates[:5]]) + (f" (+{len(dates) - 5} more)" if len(dates) > 5 else "")
    if h.end_date is not None:
        text += f" until {_fmt(h.end_date)}"
    return text


def _regular_rows(db: Session, ids) -> list[VendorHoliday]:
    return db.query(VendorHoliday).filter(
        VendorHoliday.provider_reference_id.in_(ids),
        VendorHoliday.status == "active",
        VendorHoliday.holiday_type == CASUAL,
        VendorHoliday.rule_type.in_(("weekly", "monthly")),
        or_(VendorHoliday.end_date.is_(None), VendorHoliday.end_date >= today_local()),
    ).order_by(VendorHoliday.created_at).all()


def regular_rules(db: Session, provider_ids, rows=None) -> dict:
    """{provider_id: ['Closed every Sunday', ...]} - recurring casual rules still in force."""
    out: dict = defaultdict(list)
    ids = _ids(provider_ids)
    if not ids:
        return out
    for h in rows if rows is not None else _regular_rows(db, ids):
        out[h.provider_reference_id].append(describe(h))
    return out


def weekly_off_label(weekdays) -> str | None:
    """'Weekly off: Sunday', 'Weekly off: Saturday and Sunday'."""
    days = [WEEKDAY_NAMES[d] for d in sorted(set(weekdays or []))]
    return f"Weekly off: {_join(days)}" if days else None


def public_view(db: Session, provider_ids, days: int = 30) -> dict:
    """
    What customers and delivery partners see about a kitchen's APPROVED
    holidays: the regular closures ("Closed every Sunday"), the weekly days
    off, and the closed dates in the next `days` days. Requests waiting for
    approval never show here.
    """
    given = {_uuid(p): p for p in provider_ids if p is not None}
    ids = list(given)
    today = today_local()
    calendar = closures(db, ids, today, today + timedelta(days=days))
    rows = _regular_rows(db, ids) if ids else []
    regular = regular_rules(db, ids, rows)
    weekly: dict = defaultdict(set)
    for h in rows:
        if h.rule_type == "weekly":
            weekly[h.provider_reference_id] |= set(h.weekdays or [])
    out = {}
    for pid in ids:
        upcoming = [
            {
                "date": d,
                "type": h.holiday_type,
                "label": CASUAL_LABEL if h.holiday_type == CASUAL else EMERGENCY_LABEL,
            }
            for d, h in sorted(calendar.get(pid, {}).items())
        ]
        out[given[pid]] = {
            "regular_holidays": regular.get(pid, []),
            "holiday_summary": "; ".join(regular.get(pid, [])) or None,
            # approved weekly days off, ISO weekdays (1 = Monday .. 7 = Sunday)
            "weekly_off_days": sorted(weekly.get(pid, set())),
            "weekly_off_label": weekly_off_label(weekly.get(pid)),
            "upcoming_holidays": upcoming,
            "is_closed_today": any(u["date"] == today for u in upcoming),
        }
    return out
