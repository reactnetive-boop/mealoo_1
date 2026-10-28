"""
Kitchen holidays, 28 Oct 2026:

  * an emergency holiday for some meals stays a holiday for exactly those
    meals - only breakfast + lunch + dinner (or "full day") is the whole day,
    even when fewer meals are every meal the kitchen serves (they used to be
    widened to the full day); the free skip still follows the full-day rule
    for such a holiday;
  * a regular holiday cannot be changed or removed while that would touch a
    running subscription (409 HOLIDAY_CHANGE_BLOCKED), checked when the
    kitchen asks and again when an admin approves.

Clock: Monday 5 Oct 2026, 05:00 IST (tests/conftest.py) unless a test moves it.
"""

import uuid
from datetime import date

import pytest

from app.domain import holidays
from app.models.admin_notification_model import AdminNotification
from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.models.vendor_holiday_model import VendorHoliday, VendorHolidayRequest, VendorHolidaySubscription
from tests import factories as f

API = "/api/v1"
H = f"{API}/provider/holidays"
A = f"{API}/admin/holidays"
S = f"{API}/user/subscription"
TOMORROW = date(2026, 10, 6)
SLOTS = ("breakfast", "lunch", "dinner")
ALL = "breakfast,lunch,dinner"


def _ok(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url}: {r.status_code} {r.text}"
    return r.json()


def _subscribe(client, w, *, plan=None, start="2026-10-05"):
    return _ok(client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id),
        "plan_id": str((plan or w["plan"]).subscription_plan_id),
        "address_id": str(w["address"].user_address_id),
        "start_date": start,
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    }))["subscription_id"]


def _ask(client, w, slots, day="2026-10-06"):
    return client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": day, "meal_slots": slots})


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


def _menu_holidays(client, w) -> dict:
    packages = _ok(client.get(f"{API}/user/menu/packages", headers=w["user_auth"], params={"pin_code": f.PIN}))
    return packages["packages"][0]["vendor_holidays"]


# ══ Emergency holidays for some meals ════════════════════════

@pytest.mark.parametrize("slots", [
    ["breakfast"], ["lunch"], ["dinner"], ["breakfast", "lunch"], ["breakfast", "dinner"], ["lunch", "dinner"],
])
def test_each_meal_combination_blocks_exactly_those_meals(client, db, slots):
    w = f.world(db, meal_type=ALL, plan_slot="all_slots")
    kitchen = w["kitchen"].provider_id
    sub_id = _subscribe(client, w)  # breakfast, lunch and dinner every day from today
    sent = _ok(_ask(client, w, list(reversed(slots))))
    assert sent["request"]["meal_slots"] == slots and sent["request"]["full_day"] is False

    # waiting for approval: nothing changes for customers, the kitchen or partners
    assert not any(holidays.is_slot_closed(db, kitchen, TOMORROW, s) for s in SLOTS)
    assert {o.status for o in _day(db, sub_id, TOMORROW).values()} == {"scheduled"}
    assert _menu_holidays(client, w)["upcoming_meal_closures"] == []

    h = f.approve_holiday(client, db, sent)["holiday"]
    assert h["meal_slots"] == slots and h["full_day"] is False
    stored = db.get(VendorHoliday, uuid.UUID(h["holiday_id"]))
    assert stored.meal_slots == slots  # the approval kept the meals asked for
    assert not holidays.is_closed(db, kitchen, TOMORROW)  # never the whole day

    day = _day(db, sub_id, TOMORROW)
    for slot in SLOTS:
        if slot in slots:
            assert day[slot].status == "cancelled" and day[slot].cancel_reason == "vendor_emergency_holiday"
        else:
            assert day[slot].status == "scheduled", slot  # the other meals are still cooked and delivered

    view = _menu_holidays(client, w)
    assert view["upcoming_holidays"] == []
    assert [(c["date"], c["meal_slots"]) for c in view["upcoming_meal_closures"]] == [("2026-10-06", slots)]
    open_slot = next(s for s in SLOTS if s not in slots)
    _ok(_extra(client, w, open_slot))
    assert _extra(client, w, slots[0]).json()["code"] == "KITCHEN_HOLIDAY"


def test_a_rejected_request_changes_nothing(client, db):
    w = f.world(db, meal_type=ALL, plan_slot="all_slots")
    sub_id = _subscribe(client, w)
    sent = _ok(_ask(client, w, ["lunch"]))
    _, hdr = f.admin(db)
    _ok(client.post(f"{A}/requests/{sent['request']['request_id']}/reject", headers=hdr, json={"note": "no"}))
    assert db.query(VendorHoliday).count() == 0
    assert {o.status for o in _day(db, sub_id, TOMORROW).values()} == {"scheduled"}
    assert _menu_holidays(client, w)["upcoming_meal_closures"] == []


@pytest.mark.parametrize("meal_type, slots, granted", [
    ("lunch", ["lunch"], False),                    # the only meal it serves: no skip, as for a full day
    ("lunch,dinner", ["lunch", "dinner"], True),    # every meal of a two-meal kitchen: skip, as for a full day
    ("lunch,dinner", ["dinner"], True),             # some of its meals: skip (unchanged)
])
def test_the_free_skip_of_a_holiday_for_every_meal_served_follows_the_full_day_rule(
        client, db, meal_type, slots, granted):
    w = f.world(db, meal_type=meal_type, plan_slot="lunch")
    sub_id = _subscribe(client, w)
    before = db.get(Subscription, uuid.UUID(sub_id)).free_skips_total
    sent = _ok(_ask(client, w, slots))
    assert sent["request"]["meal_slots"] == slots  # stored as chosen, never the full day
    assert sent["request"]["impact"]["free_skip"]["eligible"] is granted
    h = f.approve_holiday(client, db, sent)["holiday"]
    assert h["meal_slots"] == slots
    db.expire_all()
    assert db.get(Subscription, uuid.UUID(sub_id)).free_skips_total == before + (1 if granted else 0)
    assert db.query(VendorHolidaySubscription).one().skip_status == ("completed" if granted else "not_eligible")


# ══ Regular holidays: no change while a running plan uses it ══

def test_a_regular_holiday_cannot_be_removed_or_changed_while_a_running_plan_uses_it(client, db):
    w = f.world(db)
    rule = f.planned_holiday(db, w["kitchen"], rule_type="weekly", weekdays=[7])["holiday"]
    sub_id = _subscribe(client, w)  # 7 meal days from Mon 5 Oct: Sunday 11 Oct is a holiday inside it
    assert db.get(Subscription, uuid.UUID(sub_id)).end_date == date(2026, 10, 13)

    for r in (client.delete(f"{H}/rules/{rule['holiday_id']}", headers=w["kitchen_auth"]),
              client.put(f"{H}/rules/{rule['holiday_id']}", headers=w["kitchen_auth"], json={"preset": "weekends"})):
        body = r.json()
        assert r.status_code == 409 and body["code"] == "HOLIDAY_CHANGE_BLOCKED", body
        assert body["affected_subscriptions"] == 1 and body["clear_after"] == "2026-10-12"
        assert "1 running subscription (" in body["message"] and "12 Oct 2026" in body["message"]
    removal = client.delete(f"{H}/rules/{rule['holiday_id']}", headers=w["kitchen_auth"]).json()
    assert removal["dates"] == ["2026-10-11"] and "cannot be removed" in removal["message"]
    # nothing was sent for approval, nothing changed
    assert db.query(VendorHolidayRequest).count() == 0 and db.query(AdminNotification).count() == 0
    assert holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 11))
    listed = next(x for x in _ok(client.get(H, headers=w["kitchen_auth"]))["rules"]
                  if x["holiday_id"] == str(rule["holiday_id"]))
    assert listed["change_blocked"] is True and listed["running_subscriptions_affected"] == 1
    assert "cannot be changed or removed" in listed["change_blocked_reason"]

    # once that plan no longer runs the kitchen may ask, and an admin may approve
    db.get(Subscription, uuid.UUID(sub_id)).status = "cancelled"
    db.commit()
    listed = next(x for x in _ok(client.get(H, headers=w["kitchen_auth"]))["rules"]
                  if x["holiday_id"] == str(rule["holiday_id"]))
    assert listed["change_blocked"] is False and listed["change_blocked_reason"] is None
    sent = _ok(client.delete(f"{H}/rules/{rule['holiday_id']}", headers=w["kitchen_auth"]))
    f.approve_holiday(client, db, sent)
    db.expire_all()
    assert not holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 18))


def test_a_change_that_touches_no_running_plan_is_sent(client, db):
    w = f.world(db)
    rule = f.planned_holiday(db, w["kitchen"], rule_type="weekly", weekdays=[7])["holiday"]
    _subscribe(client, w, plan=f.plan(db, sub_type="three_day", days=3), start="2026-10-12")  # Mon-Wed
    sent = _ok(client.put(f"{H}/rules/{rule['holiday_id']}", headers=w["kitchen_auth"],
                          json={"rule_type": "weekly", "weekdays": [6]}))
    assert sent["request"]["action"] == "update" and sent["request"]["status"] == "pending"
    f.approve_holiday(client, db, sent)
    db.expire_all()
    assert holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 17))
    assert not holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 18))
    # a change moving one of that plan's days is refused
    current = _ok(client.get(H, headers=w["kitchen_auth"]))["rules"][0]
    r = client.put(f"{H}/rules/{current['holiday_id']}", headers=w["kitchen_auth"],
                   json={"rule_type": "weekly", "weekdays": [2]})
    assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_CHANGE_BLOCKED"
    assert r.json()["dates"] == ["2026-10-13"]


def test_adding_a_regular_holiday_is_not_restricted(client, db):
    w = f.world(db)
    _subscribe(client, w)
    sent = _ok(client.post(H, headers=w["kitchen_auth"], json={"preset": "every_sunday"}))
    out = f.approve_holiday(client, db, sent)
    assert out["request"]["result"]["affected_subscriptions"] == 1  # re-planned, as before


def test_older_apps_cannot_remove_a_date_a_running_plan_uses(client, db):
    w = f.world(db)
    f.planned_holiday(db, w["kitchen"], rule_type="dates", dates=["2026-10-07"])
    _subscribe(client, w)  # 5 Oct for 7 meal days: 7 Oct is a holiday inside it
    r = client.delete(f"{H}/2026-10-07", headers=w["kitchen_auth"])
    assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_CHANGE_BLOCKED"
    assert db.query(VendorHolidayRequest).count() == 0


def test_approval_is_refused_when_a_plan_started_after_the_request(client, db):
    w = f.world(db)
    rule = f.planned_holiday(db, w["kitchen"], rule_type="weekly", weekdays=[7])["holiday"]
    sent = _ok(client.delete(f"{H}/rules/{rule['holiday_id']}", headers=w["kitchen_auth"]))
    rid = sent["request"]["request_id"]
    _subscribe(client, w)  # bought while the request waited
    _, hdr = f.admin(db)
    detail = _ok(client.get(f"{A}/requests/{rid}", headers=hdr))
    assert detail["request"]["impact_now"]["blocked"] is True
    assert "cannot be removed" in detail["request"]["impact_now"]["error"]

    r = client.post(f"{A}/requests/{rid}/approve", headers=hdr, json={})
    assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_CHANGE_BLOCKED"
    db.expire_all()
    assert db.get(VendorHolidayRequest, uuid.UUID(rid)).status == "pending"
    assert db.get(VendorHoliday, uuid.UUID(str(rule["holiday_id"]))).status == "active"
    assert holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 11))
    # rejecting it leaves the approved schedule as it was
    _ok(client.post(f"{A}/requests/{rid}/reject", headers=hdr, json={"note": "Plans are running"}))
    db.expire_all()
    assert db.get(VendorHoliday, uuid.UUID(str(rule["holiday_id"]))).status == "active"
    assert holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 11))


def test_admin_provider_records_say_which_meals_a_holiday_blocks(client, db):
    w = f.world(db, meal_type=ALL, plan_slot="all_slots")
    f.approve_holiday(client, db, _ok(_ask(client, w, ["breakfast", "dinner"])))
    _, hdr = f.admin(db)
    records = _ok(client.get(f"{API}/admin/providers/{w['kitchen'].provider_id}/unavailability", headers=hdr))
    row = next(r for r in records["records"] if r["unavailable_date"] == "2026-10-06")
    assert row["meal_slots"] == ["breakfast", "dinner"] and row["full_day"] is False
