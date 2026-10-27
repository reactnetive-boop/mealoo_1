"""
Emergency holidays, 27 Oct 2026: future dates only, holidays for selected
meals, deletion by an admin only before the delivery cutoff, and the free
skip of a full-day holiday only for kitchens serving two or more meals a day.

Clock: Monday 5 Oct 2026, 05:00 IST (tests/conftest.py) unless a test moves
it. Delivery times (start of the window, IST): breakfast 07:00, lunch 12:00,
dinner 19:00. Kitchens have no time zone of their own: the business time
zone (BUSINESS_TIMEZONE, Asia/Kolkata) applies.
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import clock
from app.domain import emergency_holiday, holiday_notices, holidays, meal_offering
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.notification_model import Notification
from app.models.order_model import Order
from app.models.provider_model import MealServiceType
from app.models.provider_notification_model import ProviderNotification
from app.models.skip_credit_model import SkipCreditTransaction
from app.models.subscription_model import Subscription
from app.models.vendor_holiday_model import (
    HolidayNotice, VendorHoliday, VendorHolidayMeal, VendorHolidayRequest, VendorHolidaySubscription,
)
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from tests import factories as f

API = "/api/v1"
H = f"{API}/provider/holidays"
A = f"{API}/admin/holidays"
S = f"{API}/user/subscription"
TODAY = date(2026, 10, 5)  # a Monday
TOMORROW = date(2026, 10, 6)
ALL = "breakfast,lunch,dinner"
UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")


def _ok(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url}: {r.status_code} {r.text}"
    return r.json()


def _kitchen(db, meal_type=ALL, plan_slot="all_slots", **kw):
    """A kitchen selling one package served at `meal_type`, a 7-day plan for `plan_slot`, a customer with money."""
    return f.world(db, meal_type=meal_type, plan_slot=plan_slot, **kw)


def _subscribe(client, w, *, user_auth=None, address=None, plan=None, start="2026-10-05"):
    return _ok(client.post(S, headers=user_auth or w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id),
        "plan_id": str((plan or w["plan"]).subscription_plan_id),
        "address_id": str((address or w["address"]).user_address_id),
        "start_date": start,
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    }))["subscription_id"]


def _ask(client, w, day="2026-10-06", slots=None, **extra):
    body = {"date": day, **extra}
    if slots is not None:
        body["meal_slots"] = slots
    return client.post(f"{H}/emergency", headers=w["kitchen_auth"], json=body)


def _holiday(client, db, w, day="2026-10-06", slots=None) -> dict:
    """An emergency holiday the kitchen asked for and an admin approved."""
    return f.approve_holiday(client, db, _ok(_ask(client, w, day, slots)))["holiday"]


def _delete(client, db, holiday_id, reason="The kitchen can cook after all"):
    _, hdr = f.admin(db)
    return client.request("DELETE", f"{A}/{holiday_id}", headers=hdr, json={"reason": reason})


def _extra(client, w, slot, day="2026-10-06"):
    return client.post(f"{API}/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": day, "meal_slot": slot,
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })


def _day(db, sub_id, on) -> dict:
    db.expire_all()
    rows = db.query(Order).filter(Order.subscription_reference_id == uuid.UUID(str(sub_id)), Order.order_date == on)
    return {o.meal_slot: o for o in rows}


def _balance(db, user) -> Decimal:
    db.expire_all()
    return db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance


def _sub(db, sub_id) -> Subscription:
    db.expire_all()
    return db.get(Subscription, uuid.UUID(str(sub_id)))


# ══ Part 1: future dates only ════════════════════════════════

def test_tomorrow_can_be_asked_for(client, db):
    w = _kitchen(db)
    preview = _ok(client.get(f"{H}/emergency/preview", headers=w["kitchen_auth"], params={"date": "2026-10-06"}))
    assert preview["date"] == "2026-10-06" and preview["full_day"] is True
    sent = _ok(_ask(client, w))
    assert sent["request"]["holiday_date"] == "2026-10-06" and sent["request"]["status"] == "pending"


@pytest.mark.parametrize("day, state", [("2026-10-05", "today"), ("2026-10-04", "in the past")])
def test_today_and_past_dates_are_refused(client, db, day, state):
    w = _kitchen(db)
    r = _ask(client, w, day)
    assert r.status_code == 422 and r.json()["code"] == "HOLIDAY_NOT_FUTURE"
    message = r.json()["message"]
    assert message.startswith("Emergency holidays can only be created for future dates.") and state in message
    assert date.fromisoformat(day).strftime("%d %b %Y") in message  # the failing date is named
    # the preview follows the same rule, and nothing was stored or sent to the admins
    preview = client.get(f"{H}/emergency/preview", headers=w["kitchen_auth"], params={"date": day})
    assert preview.status_code == 422 and preview.json()["code"] == "HOLIDAY_NOT_FUTURE"
    assert db.query(VendorHolidayRequest).count() == 0 and db.query(HolidayNotice).count() == 0


def test_a_request_without_a_date_means_today_and_is_refused(client, db):
    w = _kitchen(db)
    r = client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"reason": "gas leak"})
    assert r.status_code == 422 and r.json()["code"] == "HOLIDAY_NOT_FUTURE" and "is today" in r.json()["message"]


def test_tomorrow_in_utc_but_today_in_the_business_timezone_is_refused(client, db):
    w = _kitchen(db)
    clock.freeze(datetime(2026, 10, 6, 2, 0))  # 02:00 IST on 6 Oct = 20:30 UTC on 5 Oct
    assert clock.now_utc().date() == date(2026, 10, 5)  # 6 Oct is "tomorrow" in UTC
    r = _ask(client, w, "2026-10-06")
    assert r.status_code == 422 and r.json()["code"] == "HOLIDAY_NOT_FUTURE" and "is today" in r.json()["message"]
    assert _ok(_ask(client, w, "2026-10-07"))["request"]["holiday_date"] == "2026-10-07"


# ══ Part 2: holidays for selected meals ══════════════════════

def test_a_single_meal_can_be_blocked(client, db):
    w = _kitchen(db)
    kitchen = w["kitchen"].provider_id
    sent = _ok(_ask(client, w, slots=["lunch"]))
    assert sent["request"]["meal_slots"] == ["lunch"] and sent["request"]["full_day"] is False
    assert sent["request"]["label"] == "Emergency holiday on 6 Oct 2026 (Lunch only)"
    assert sent["request"]["impact"]["meal_slots"] == ["lunch"]
    h = f.approve_holiday(client, db, sent)["holiday"]
    assert h["meal_slots"] == ["lunch"] and h["full_day"] is False and h["meals_label"] == "Lunch"
    assert h["label"] == "Emergency closure on 6 Oct 2026 (Lunch only)"
    assert holidays.is_slot_closed(db, kitchen, TOMORROW, "lunch")
    assert not holidays.is_slot_closed(db, kitchen, TOMORROW, "breakfast")
    assert not holidays.is_slot_closed(db, kitchen, TOMORROW, "dinner")
    assert not holidays.is_closed(db, kitchen, TOMORROW)  # the kitchen is open that day
    # listings: the kitchen's calendar row, the admin's list
    overview = _ok(client.get(H, headers=w["kitchen_auth"]))
    row = next(c for c in overview["calendar"] if c["date"] == "2026-10-06")
    assert row["full_day"] is False and row["meal_slots"] == ["lunch"] and "Lunch" in row["label"]
    assert overview["offered_meal_slots"] == ["breakfast", "lunch", "dinner"]
    _, hdr = f.admin(db)
    listed = _ok(client.get(A, headers=hdr, params={"holiday_type": "emergency"}))["holidays"][0]
    assert listed["meal_slots"] == ["lunch"] and listed["deletable"] is True


def test_several_meals_can_be_blocked_in_any_order(client, db):
    w = _kitchen(db)
    kitchen = w["kitchen"].provider_id
    sent = _ok(_ask(client, w, slots=["dinner", "Breakfast"]))
    assert sent["request"]["meal_slots"] == ["breakfast", "dinner"]
    assert sent["request"]["label"].endswith("(Breakfast and Dinner only)")
    assert f.approve_holiday(client, db, sent)["holiday"]["meal_slots"] == ["breakfast", "dinner"]
    assert holidays.is_slot_closed(db, kitchen, TOMORROW, "breakfast")
    assert holidays.is_slot_closed(db, kitchen, TOMORROW, "dinner")
    assert not holidays.is_slot_closed(db, kitchen, TOMORROW, "lunch")


@pytest.mark.parametrize("meal_type, slots", [
    (ALL, None),                              # nothing chosen: the whole day (older apps)
    (ALL, ["breakfast", "lunch", "dinner"]),  # every meal
    (ALL, ["full_day"]),                      # the "Full day" option
    ("lunch,dinner", ["dinner", "lunch"]),    # every meal THIS kitchen serves
])
def test_every_meal_the_kitchen_serves_is_the_full_day(client, db, meal_type, slots):
    w = _kitchen(db, meal_type=meal_type, plan_slot="lunch")
    sent = _ok(_ask(client, w, slots=slots))
    assert sent["request"]["meal_slots"] is None and sent["request"]["full_day"] is True
    assert sent["request"]["label"] == "Emergency holiday on 6 Oct 2026"
    # stored exactly like a full-day holiday always was
    assert db.query(VendorHolidayRequest).one().dedupe_key == "emergency:2026-10-06"
    h = f.approve_holiday(client, db, sent)["holiday"]
    assert h["meal_slots"] is None and h["full_day"] is True and h["label"] == "Emergency closure on 6 Oct 2026"
    assert holidays.is_closed(db, w["kitchen"].provider_id, TOMORROW)


def test_meals_the_kitchen_does_not_serve_are_refused(client, db):
    w = _kitchen(db, meal_type="lunch,dinner", plan_slot="lunch")
    r = _ask(client, w, slots=["breakfast", "lunch"])
    assert r.status_code == 422 and r.json()["code"] == "HOLIDAY_SLOT_NOT_OFFERED"
    assert "does not serve Breakfast" in r.json()["message"] and "Lunch and Dinner" in r.json()["message"]
    unknown = _ask(client, w, slots=["brunch"])
    assert unknown.status_code == 422 and unknown.json()["code"] == "HOLIDAY_SLOT_UNKNOWN"
    empty = _ask(client, w, slots=[])
    assert empty.status_code == 422 and empty.json()["code"] == "HOLIDAY_MEALS_REQUIRED"
    preview = client.get(f"{H}/emergency/preview", headers=w["kitchen_auth"],
                         params={"date": "2026-10-06", "meal_slots": "breakfast"})
    assert preview.status_code == 422 and preview.json()["code"] == "HOLIDAY_SLOT_NOT_OFFERED"
    assert db.query(VendorHolidayRequest).count() == 0
    assert _ok(client.get(H, headers=w["kitchen_auth"]))["offered_meal_slots"] == ["lunch", "dinner"]


def test_the_same_meal_cannot_be_blocked_twice(client, db):
    w = _kitchen(db)
    _holiday(client, db, w, slots=["lunch"])
    for slots in (["lunch"], ["lunch", "dinner"], None):
        r = _ask(client, w, slots=slots)
        assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_EXISTS", slots
    assert "Lunch on 06 Oct 2026" in _ask(client, w, slots=["lunch", "dinner"]).json()["message"]
    # another meal of that day is fine; the same waiting request is given back, an overlapping one refused
    dinner = _ok(_ask(client, w, slots=["dinner"]))
    assert _ok(_ask(client, w, slots=["dinner"]))["duplicate"] is True
    clash = _ask(client, w, slots=["breakfast", "dinner"])
    assert clash.status_code == 409 and clash.json()["code"] == "HOLIDAY_REQUEST_PENDING"
    breakfast = _ok(_ask(client, w, slots=["breakfast"]))
    assert breakfast["duplicate"] is False
    f.approve_holiday(client, db, dinner)
    f.approve_holiday(client, db, breakfast)
    rows = db.query(VendorHoliday).filter(VendorHoliday.start_date == TOMORROW).all()
    assert sorted(tuple(h.meal_slots) for h in rows) == [("breakfast",), ("dinner",), ("lunch",)]


def test_the_database_refuses_two_holidays_for_the_same_meal(db):
    kitchen, _ = f.provider(db)

    def holiday(slots):
        return VendorHoliday(provider_reference_id=kitchen.provider_id, holiday_type="emergency", rule_type="dates",
                             dates=[TOMORROW], start_date=TOMORROW, end_date=TOMORROW, meal_slots=slots,
                             status="active", processing_status="completed")

    db.add(holiday(["lunch"]))
    db.commit()
    db.add(holiday(["dinner"]))
    db.commit()
    for slots in (["breakfast", "lunch"], None, ["brunch"], []):
        db.add(holiday(slots))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    # a deleted holiday frees its meal
    db.query(VendorHoliday).filter(VendorHoliday.meal_slots == ["lunch"]).update({"status": "removed"})
    db.commit()
    db.add(holiday(["lunch"]))
    db.commit()


def test_a_lunch_only_holiday_blocks_lunch_while_breakfast_and_dinner_are_delivered(client, db):
    w = _kitchen(db, balance="5000")
    kitchen = w["kitchen"].provider_id
    boy, _ = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _subscribe(client, w)  # breakfast, lunch and dinner every day from today
    before = _balance(db, w["user"])
    _holiday(client, db, w, slots=["lunch"])

    meals = _day(db, sub_id, TOMORROW)
    assert meals["lunch"].status == "cancelled" and meals["lunch"].cancel_reason == "vendor_emergency_holiday"
    assert meals["lunch"].refund_amount == Decimal("180.00")
    assert meals["breakfast"].status == "scheduled" and meals["dinner"].status == "scheduled"
    assert {o.status for o in _day(db, sub_id, TODAY).values()} == {"scheduled"}
    assert _balance(db, w["user"]) - before == Decimal("180.00")
    views = {o["meal_slot"]: o for o in _ok(client.get(f"{S}/{sub_id}/orders", headers=w["user_auth"]))["orders"]
             if o["order_date"] == "2026-10-06"}
    assert views["lunch"]["holiday_outcome"]["meal_slots"] == ["lunch"]
    assert views["lunch"]["holiday_outcome"]["skips_credited"] == 1
    assert views["breakfast"]["holiday_outcome"] is None and views["dinner"]["holiday_outcome"] is None

    # the kitchen prepares and hands over breakfast and dinner; lunch has nothing to mark
    lunch = client.put(f"{API}/provider/orders/batch/status", headers=w["kitchen_auth"],
                       json={"order_date": "2026-10-06", "meal_slot": "lunch", "status": "ready_for_pickup"})
    assert lunch.status_code == 409 and lunch.json()["code"] == "KITCHEN_HOLIDAY"
    for slot in ("breakfast", "dinner"):
        done = _ok(client.put(f"{API}/provider/orders/batch/status", headers=w["kitchen_auth"],
                              json={"order_date": "2026-10-06", "meal_slot": slot, "status": "ready_for_pickup"}))
        assert done["changed"] == 1
    meals = _day(db, sub_id, TOMORROW)
    assert meals["breakfast"].status == meals["dinner"].status == "ready_for_pickup"
    assert meals["lunch"].status == "cancelled"

    # one-time orders: lunch refused, dinner taken
    assert _extra(client, w, "lunch").json()["code"] == "KITCHEN_HOLIDAY"
    _ok(_extra(client, w, "dinner"))

    # the customer is told which meal; the partner that no lunch pickup is needed
    note = db.query(Notification).filter(Notification.user_reference_id == w["user"].user_id,
                                         Notification.type == "vendor_holiday_compensation").one()
    assert note.title == "No lunch from your kitchen on 06 Oct 2026"
    assert "cannot serve lunch on 06 Oct 2026" in note.body and "Other meals that day are not affected" in note.body
    assert "₹180.00 for 1 meal" in note.body and note.data["meal_slots"] == ["lunch"]
    partner = db.query(DeliveryBoyNotification).filter(
        DeliveryBoyNotification.delivery_boy_reference_id == boy.delivery_boy_id,
        DeliveryBoyNotification.title.like("%no lunch%"),
    ).one()
    assert "No lunch pickup is required" in partner.body

    # customers and partners see one blocked meal, not a closed day
    view = holidays.public_view(db, [kitchen])[kitchen]
    assert view["upcoming_holidays"] == [] and view["is_closed_today"] is False
    assert view["upcoming_meal_closures"] == [{
        "date": TOMORROW, "type": "emergency", "meal_slots": ["lunch"], "label": "Vendor emergency holiday – Lunch",
    }]


def test_a_plan_bought_after_the_holiday_gets_only_the_blocked_meal_refunded(client, db):
    w = _kitchen(db, balance="10000")
    _holiday(client, db, w, slots=["lunch"])
    sub_id = _subscribe(client, w)  # bought after the approval; covers 6 Oct
    meals = _day(db, sub_id, TOMORROW)
    assert meals["lunch"].status == "cancelled" and meals["lunch"].refund_amount == Decimal("180.00")
    assert meals["breakfast"].status == "scheduled" and meals["dinner"].status == "scheduled"
    assert TOMORROW not in holidays.sub_holidays(_sub(db, sub_id))  # still a meal day of the plan
    refund = db.query(WalletTransaction).filter(
        WalletTransaction.idempotency_key == f"meal_refund:{meals['lunch'].order_id}").one()
    assert refund.amount == Decimal("180.00")
    assert db.query(VendorHolidayMeal).filter(
        VendorHolidayMeal.order_reference_id == meals["lunch"].order_id).one().outcome == "compensated"
    holiday_notices.deliver(db)
    note = db.query(Notification).filter(Notification.user_reference_id == w["user"].user_id,
                                         Notification.type == "vendor_holiday_compensation").one()
    assert "cannot serve lunch" in note.body and "₹180.00" in note.body

    # a lunch-only plan has no meal at all that day: the day moves to the end of the plan, uncharged
    lunch_plan = f.plan(db, slot="lunch")
    user, address, user_auth = f.customer(db, balance="5000")
    sub2 = _subscribe(client, w, plan=lunch_plan, user_auth=user_auth, address=address)
    s2 = _sub(db, sub2)
    assert TOMORROW in holidays.sub_holidays(s2) and _day(db, sub2, TOMORROW) == {}
    assert s2.end_date == TODAY + timedelta(days=8)


def test_holidays_from_before_the_migration_still_close_the_whole_day(client, db):
    w = _kitchen(db, balance="5000")
    kitchen = w["kitchen"].provider_id
    # what every holiday existing before the migration looks like: meal_slots NULL
    legacy = VendorHoliday(provider_reference_id=kitchen, holiday_type="emergency", rule_type="dates",
                           dates=[TOMORROW], start_date=TOMORROW, end_date=TOMORROW, status="active",
                           processing_status="completed", created_by_type="migration")
    db.add(legacy)
    db.commit()
    stored = db.execute(text("SELECT meal_slots FROM provider.vendor_holidays WHERE vendor_holiday_id = :i"),
                        {"i": legacy.vendor_holiday_id}).scalar()
    assert stored is None
    assert holidays.is_closed(db, kitchen, TOMORROW)
    assert all(holidays.is_slot_closed(db, kitchen, TOMORROW, s) for s in ("breakfast", "lunch", "dinner"))
    assert holidays.holiday_slots(legacy) == ["breakfast", "lunch", "dinner"]
    assert holidays.describe(legacy) == "Emergency closure on 6 Oct 2026"
    for slots in (["breakfast"], None):
        assert _ask(client, w, slots=slots).json()["code"] == "HOLIDAY_EXISTS"
    assert _extra(client, w, "dinner").json()["code"] == "KITCHEN_HOLIDAY"
    # a plan bought now skips the day entirely, as before
    sub_id = _subscribe(client, w)
    assert _day(db, sub_id, TOMORROW) == {} and TOMORROW in holidays.sub_holidays(_sub(db, sub_id))
    row = next(c for c in _ok(client.get(H, headers=w["kitchen_auth"]))["calendar"] if c["date"] == "2026-10-06")
    assert row["full_day"] is True and row["meal_slots"] is None
    # deletion: the earliest meal the kitchen serves (breakfast, 07:00)
    assert emergency_holiday.delete_cutoff(db, legacy) == datetime(2026, 10, 6, 7, 0, tzinfo=IST)


# ══ Part 3: deletion only before the delivery cutoff ═════════

def test_an_admin_deletes_an_emergency_holiday_before_the_delivery_cutoff(client, db):
    w = _kitchen(db, meal_type="lunch,dinner", plan_slot="lunch_dinner", balance="5000")
    kitchen = w["kitchen"].provider_id
    sub_id = _subscribe(client, w)
    h = _holiday(client, db, w)  # the whole of 6 Oct; earliest meal: lunch at 12:00
    skips, balance = _sub(db, sub_id).free_skips_total, _balance(db, w["user"])
    _, hdr = f.admin(db)
    detail = _ok(client.get(f"{A}/{h['holiday_id']}", headers=hdr))["holiday"]
    assert detail["deletable"] is True and detail["delete_cutoff_at"] == "2026-10-06T12:00:00+05:30"

    clock.freeze(datetime(2026, 10, 6, 11, 59, 59))
    out = _ok(_delete(client, db, h["holiday_id"]))
    assert out["holiday"]["status"] == "removed" and out["holiday"]["deletable"] is False
    assert out["holiday"]["removed_reason"] == "The kitchen can cook after all"
    assert not holidays.is_closed(db, kitchen, TOMORROW)
    # what was given stays with the customer; cancelled meals stay cancelled
    assert _balance(db, w["user"]) == balance and _sub(db, sub_id).free_skips_total == skips
    assert {o.status for o in _day(db, sub_id, TOMORROW).values()} == {"cancelled"}
    # the customer and the kitchen hear it is open again
    note = db.query(Notification).filter(Notification.user_reference_id == w["user"].user_id,
                                         Notification.title == "Your kitchen is open again today").one()
    assert "all meals can be ordered again" in note.body and "stay with you" in note.body
    assert db.query(ProviderNotification).filter(ProviderNotification.title == "Emergency holiday cancelled").count() == 1
    # the day can be ordered for again; a second delete changes nothing
    _ok(_extra(client, w, "dinner"))
    again = _delete(client, db, h["holiday_id"])
    assert again.status_code == 409 and again.json()["code"] == "HOLIDAY_ALREADY_DELETED"
    # retries of the deleted holiday do nothing more
    assert emergency_holiday.process(db, uuid.UUID(h["holiday_id"]))["removed"] is True


@pytest.mark.parametrize("at", [
    datetime(2026, 10, 6, 12, 0, 0),  # exactly the delivery time of lunch
    datetime(2026, 10, 6, 12, 0, 1),
    datetime(2026, 10, 7, 9, 0),
])
def test_at_or_after_the_delivery_cutoff_nothing_is_deleted(client, db, at):
    w = _kitchen(db, meal_type="lunch,dinner", plan_slot="lunch")
    _subscribe(client, w)
    h = _holiday(client, db, w)
    notices = db.query(HolidayNotice).count()
    clock.freeze(at)
    r = _delete(client, db, h["holiday_id"])
    assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_DELETE_CUTOFF_PASSED"
    assert r.json()["message"] == "This emergency holiday can no longer be deleted because the delivery cutoff has passed."
    db.expire_all()
    row = db.get(VendorHoliday, uuid.UUID(h["holiday_id"]))
    assert row.status == "active" and row.removed_at is None and row.removed_by is None
    assert db.query(HolidayNotice).count() == notices
    assert holidays.is_closed(db, w["kitchen"].provider_id, TOMORROW)
    _, hdr = f.admin(db)
    assert _ok(client.get(f"{A}/{h['holiday_id']}", headers=hdr))["holiday"]["deletable"] is False


def test_a_holiday_for_some_meals_can_be_deleted_until_its_earliest_selected_meal(client, db):
    w = _kitchen(db)  # serves breakfast (07:00), lunch (12:00) and dinner (19:00)
    lunch_dinner = _holiday(client, db, w, "2026-10-06", ["dinner", "lunch"])
    dinner = _holiday(client, db, w, "2026-10-07", ["dinner"])
    full = _holiday(client, db, w, "2026-10-08")
    cutoff = {h["holiday_id"]: emergency_holiday.delete_cutoff(db, db.get(VendorHoliday, uuid.UUID(h["holiday_id"])))
              for h in (lunch_dinner, dinner, full)}
    assert cutoff[lunch_dinner["holiday_id"]] == datetime(2026, 10, 6, 12, 0, tzinfo=IST)  # lunch, not breakfast
    assert cutoff[dinner["holiday_id"]] == datetime(2026, 10, 7, 19, 0, tzinfo=IST)
    assert cutoff[full["holiday_id"]] == datetime(2026, 10, 8, 7, 0, tzinfo=IST)  # earliest meal served
    clock.freeze(datetime(2026, 10, 6, 11, 30))  # breakfast is out; lunch not yet
    _ok(_delete(client, db, lunch_dinner["holiday_id"]))
    clock.freeze(datetime(2026, 10, 7, 18, 59))
    _ok(_delete(client, db, dinner["holiday_id"]))
    clock.freeze(datetime(2026, 10, 8, 7, 0))
    assert _delete(client, db, full["holiday_id"]).json()["code"] == "HOLIDAY_DELETE_CUTOFF_PASSED"


def test_the_cutoff_is_business_local_time_never_utc(client, db):
    w = _kitchen(db, meal_type="lunch,dinner", plan_slot="lunch")
    h = _holiday(client, db, w, slots=["lunch"])  # lunch on 6 Oct: 12:00 IST = 06:30 UTC
    clock.freeze(datetime(2026, 10, 6, 11, 0, tzinfo=UTC))  # before noon in UTC, 16:30 in India: too late
    assert _delete(client, db, h["holiday_id"]).json()["code"] == "HOLIDAY_DELETE_CUTOFF_PASSED"
    clock.freeze(datetime(2026, 10, 6, 6, 29, tzinfo=UTC))  # 11:59 in India
    _ok(_delete(client, db, h["holiday_id"]))


def test_a_business_in_another_timezone_uses_its_own_delivery_time(client, db, monkeypatch):
    w = _kitchen(db, meal_type="lunch,dinner", plan_slot="lunch")
    h = _holiday(client, db, w, slots=["lunch"])
    monkeypatch.setattr(clock, "BUSINESS_TZ", ZoneInfo("America/New_York"))
    cutoff = emergency_holiday.delete_cutoff(db, db.get(VendorHoliday, uuid.UUID(h["holiday_id"])))
    assert cutoff.astimezone(UTC) == datetime(2026, 10, 6, 16, 0, tzinfo=UTC)  # noon in New York (EDT)
    clock.freeze(datetime(2026, 10, 6, 16, 0, tzinfo=UTC))  # exactly noon there
    assert _delete(client, db, h["holiday_id"]).json()["code"] == "HOLIDAY_DELETE_CUTOFF_PASSED"
    clock.freeze(datetime(2026, 10, 6, 15, 59, tzinfo=UTC))  # 11:59 there, long after lunch in India
    _ok(_delete(client, db, h["holiday_id"]))


def test_only_emergency_holidays_are_deleted_here(client, db):
    w = _kitchen(db)
    regular = f.planned_holiday(db, w["kitchen"], rule_type="dates", dates=["2026-10-08"])
    r = _delete(client, db, regular["holiday"]["holiday_id"])
    assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_NOT_EMERGENCY"
    assert _delete(client, db, uuid.uuid4()).status_code == 404


# ══ Part 4: free skip of a full-day holiday ══════════════════

@pytest.mark.parametrize("meal_type, granted", [(ALL, True), ("lunch,dinner", True), ("lunch", False)])
def test_a_full_day_holiday_grants_the_free_skip_only_from_two_meals_a_day(client, db, caplog, meal_type, granted):
    caplog.set_level(logging.INFO, logger="app.holidays")
    w = _kitchen(db, meal_type=meal_type, plan_slot="lunch", balance="5000")
    sub_id = _subscribe(client, w)
    skips, before = _sub(db, sub_id).free_skips_total, _balance(db, w["user"])
    sent = _ok(_ask(client, w))
    impact = sent["request"]["impact"]
    assert impact["free_skip"]["eligible"] is granted and impact["skip_credits"] == (1 if granted else 0)
    hid = f.approve_holiday(client, db, sent)["holiday"]["holiday_id"]

    assert _sub(db, sub_id).free_skips_total == skips + (1 if granted else 0)
    assert db.query(SkipCreditTransaction).count() == (1 if granted else 0)
    row = db.query(VendorHolidaySubscription).one()
    assert row.skip_status == ("completed" if granted else "not_eligible") and row.notice_queued_at is not None
    # the meal of that day is refunded either way, and the customer is told
    assert _balance(db, w["user"]) - before == Decimal("180.00")
    note = db.query(Notification).filter(Notification.user_reference_id == w["user"].user_id,
                                         Notification.type == "vendor_holiday_compensation").one()
    assert ("1 extra free meal skip" in note.body) is granted
    assert note.data["skips_credited"] == (1 if granted else 0)
    assert db.get(VendorHoliday, uuid.UUID(hid)).processing_status == "completed"
    # the plan's calendar says the same
    orders = _ok(client.get(f"{S}/{sub_id}/orders", headers=w["user_auth"]))["orders"]
    outcome = next(o["holiday_outcome"] for o in orders if o["order_date"] == "2026-10-06")
    assert outcome["outcome"] == "compensated" and outcome["skips_credited"] == (1 if granted else 0)
    assert outcome["meal_slots"] is None
    # the reason is logged when no skip is granted
    logged = [r.getMessage() for r in caplog.records if "no free skip" in r.getMessage()]
    assert bool(logged) is not granted
    if not granted:
        assert "1 meal(s) on Tuesday (lunch)" in logged[0]
        # a retry never grants it later
        emergency_holiday.process(db, uuid.UUID(hid), retry_failed=True)
        assert db.query(SkipCreditTransaction).count() == 0


def test_a_holiday_for_some_meals_keeps_the_free_skip(client, db):
    w = _kitchen(db, plan_slot="lunch")
    sub_id = _subscribe(client, w)
    skips = _sub(db, sub_id).free_skips_total
    _holiday(client, db, w, slots=["dinner"])
    assert _sub(db, sub_id).free_skips_total == skips + 1
    assert db.query(VendorHolidaySubscription).one().skip_status == "completed"


def test_free_skip_eligibility_reads_the_standard_meals_for_the_holiday_weekday(db):
    """No per-weekday meal setting exists: every weekday is judged by the standard set, named by its weekday."""
    kitchen, _ = f.provider(db)
    cat = f.category(db)
    f.package(db, kitchen, cat, meal_type="lunch")
    f.package(db, kitchen, cat, meal_type="dinner")
    f.package(db, kitchen, cat, meal_type="breakfast", approved=False)  # not sellable: not counted
    week = [TODAY + timedelta(days=i) for i in range(7)]
    results = [meal_offering.free_skip_eligibility(db, kitchen.provider_id, d) for d in week]
    assert {r.slots for r in results} == {("lunch", "dinner")} and all(r.eligible for r in results)
    assert [r.reason.rsplit(" on ", 1)[1] for r in results] == [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    ]
    # without a sellable package the profile's meal service type is the standard set
    other, _ = f.provider(db)
    for service, eligible in ((MealServiceType.LUNCH, False), (MealServiceType.LUNCH_AND_DINNER, True),
                              (MealServiceType.FULL_DAY, True)):
        other.meal_service_type = service
        db.commit()
        r = meal_offering.free_skip_eligibility(db, other.provider_id, date(2026, 10, 11))
        assert r.eligible is eligible and "on Sunday" in r.reason, service
