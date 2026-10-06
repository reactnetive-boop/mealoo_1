"""
Single source of "now" for business logic.

Meal dates, cut-offs and the midnight jobs are all defined in the business
timezone (IST by default), regardless of where the server runs. Never call
date.today() / datetime.now() directly in business code: on a UTC server they
are off by 5h30 and orders land on the wrong day.
"""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from app.core.config import BUSINESS_TIMEZONE

BUSINESS_TZ = ZoneInfo(BUSINESS_TIMEZONE)

# Tests pin the clock through freeze(); production never sets it.
_frozen: datetime | None = None


def freeze(at: datetime | None) -> None:
    global _frozen
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=BUSINESS_TZ)
    _frozen = at


def now_utc() -> datetime:
    if _frozen is not None:
        return _frozen.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def now_local() -> datetime:
    """Current wall-clock time in the business timezone (tz-aware)."""
    return now_utc().astimezone(BUSINESS_TZ)


def today_local() -> date:
    return now_local().date()


def local_datetime(on: date, at: time) -> datetime:
    """A tz-aware datetime for a business-local date and time."""
    return datetime.combine(on, at, tzinfo=BUSINESS_TZ)


def to_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BUSINESS_TZ)
