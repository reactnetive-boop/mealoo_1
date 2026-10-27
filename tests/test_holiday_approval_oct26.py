"""
Kitchen holiday requests approved by an admin (2026-10-26): emergency and
regular (weekly) holidays, the shared approval flow, refunds, the free skip
for every active subscription, notices to admins, kitchens, customers and
delivery partners, plan meal counts, duplicates, failures and retries.

Clock: Monday 5 Oct 2026, 05:00 IST (tests/conftest.py) unless a test moves it.
"""

import threading
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core import clock
from app.core.database import SessionLocal
from app.domain import holiday_notices, holidays
from app.models.admin_notification_model import AdminNotification
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.extra_order_model import ExtraOrder
from app.models.notification_model import Notification
from app.models.order_model import Order
from app.models.provider_notification_model import ProviderNotification
from app.models.skip_credit_model import SkipCreditTransaction
from app.models.subscription_model import Subscription
from app.models.vendor_holiday_model import (
    HolidayNotice, VendorHoliday, VendorHolidayRequest, VendorHolidaySubscription,
)
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from app.schedulers import jobs
from app.services.holiday_request_service import HolidayRequestService
from tests import factories as f

API = "/api/v1"
H = f"{API}/provider/holidays"
R = f"{API}/admin/holidays/requests"
S = f"{API}/user/subscription"
TODAY = date(2026, 10, 5)  # a Monday
SUNDAY = date(2026, 10, 11)


@pytest.fixture(autouse=True)
def _two_meal_kitchens(monkeypatch):
    """These kitchens serve lunch and dinner, so a full-day emergency grants the free skip."""
    f.serve_two_meals(monkeypatch)


def _ok(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url}: {r.status_code} {r.text}"
    return r.json()


def _subscribe(client, w, *, user_auth=None, address=None, plan=None, start="2026-10-05", **extra):
    return _ok(client.post(S, headers=user_auth or w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id),
        "plan_id": str((plan or w["plan"]).subscription_plan_id),
        "address_id": str((address or w["address"]).user_address_id),
        "start_date": start,
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
        **extra,
    }))["subscription_id"]


def _extra_order(client, w, day="2026-10-05", user_auth=None, address=None):
    return client.post(f"{API}/user/order/extra", headers=user_auth or w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id),
        "address_id": str((address or w["address"]).user_address_id),
        "delivery_date": day, "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })


def _balance(db, user) -> Decimal:
    db.expire_all()
    return db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance


def _meals(db, sub_id, *statuses):
    db.expire_all()
    q = db.query(Order).filter(Order.subscription_reference_id == sub_id)
    if statuses:
        q = q.filter(Order.status.in_(statuses))
    return q.order_by(Order.order_date).all()


def _second_customer(db, balance="5000"):
    user, address, auth = f.customer(db, balance=balance)
    return {"user": user, "address": address, "user_auth": auth}


# ══ Shared approval flow ═════════════════════════════════════

def test_pending_and_rejected_requests_never_change_the_approved_schedule(client, db):
    w = f.world(db, balance="5000", plan_days=14)
    boy, _ = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _subscribe(client, w)
    end = db.get(Subscription, uuid.UUID(sub_id)).end_date
    _, admin_hdr = f.admin(db)

    sent = _ok(client.post(H, headers=w["kitchen_auth"], json={"preset": "every_sunday", "reason": "family day"}))
    assert sent["request"]["status"] == "pending" and sent["request"]["label"] == "Add: Closed every Sunday"
    emergency = _ok(client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": "2026-10-07"}))
    # nothing changed while they wait
    assert not holidays.is_closed(db, w["kitchen"].provider_id, SUNDAY)
    assert not holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 7))
    assert {m.order_date for m in _meals(db, sub_id, "scheduled")} >= {SUNDAY, date(2026, 10, 7)}
    assert db.get(Subscription, uuid.UUID(sub_id)).end_date == end
    assert _ok(_extra_order(client, w, day=SUNDAY.isoformat()))  # a Sunday can still be ordered
    listing = _ok(client.get(f"{API}/user/menu/packages", headers=w["user_auth"], params={"pin_code": f.PIN}))
    assert listing["packages"][0]["vendor_holidays"]["weekly_off_days"] == []
    boy_auth = f.auth(__import__("app.core.security", fromlist=["x"]).create_access_token(
        {"delivery_boy_id": str(boy.delivery_boy_id)}, role="delivery_boy", token_version=0))
    vendor = _ok(client.get(f"{API}/delivery/vendors/{w['kitchen'].provider_id}", headers=boy_auth))["vendor"]
    assert vendor["holidays"]["weekly_off_days"] == []
    assert db.query(Notification).filter(Notification.type.like("vendor_holiday%")).count() == 0

    # the kitchen sees both waiting
    overview = _ok(client.get(H, headers=w["kitchen_auth"]))
    assert len(overview["pending_requests"]) == 2 and overview["rules"] == []

    for req in (sent, emergency):
        rid = req["request"]["request_id"]
        out = _ok(client.post(f"{R}/{rid}/reject", headers=admin_hdr, json={"note": "Too many kitchens closed"}))
        assert out["request"]["status"] == "rejected"
        # a decided request cannot be approved any more
        late = client.post(f"{R}/{rid}/approve", headers=admin_hdr, json={})
        assert late.status_code == 409 and late.json()["code"] == "HOLIDAY_REQUEST_DECIDED"
    db.expire_all()
    assert not holidays.is_closed(db, w["kitchen"].provider_id, SUNDAY)
    assert db.get(Subscription, uuid.UUID(sub_id)).end_date == end
    assert db.query(VendorHoliday).count() == 0
    notes = db.query(ProviderNotification).filter(ProviderNotification.title == "Holiday request rejected").all()
    assert len(notes) == 2 and all("Too many kitchens closed" in n.body for n in notes)


def test_admins_are_told_at_once_with_the_date_and_the_changes(client, db):
    w = f.world(db, balance="5000")
    a1, a1_hdr = f.admin(db)
    a2, _ = f.admin(db)
    _subscribe(client, w)
    sent = _ok(client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": "2026-10-06", "reason": "gas leak"}))
    rows = db.query(AdminNotification).all()
    assert {r.admin_user_reference_id for r in rows} == {a1.admin_user_id, a2.admin_user_id}
    body = rows[0].body
    assert "emergency holiday on Tue 06 Oct 2026" in body and "gas leak" in body
    assert "1 meal(s)" in body and "1 active subscription(s) get 1 extra free skip" in body
    assert rows[0].data["request_id"] == sent["request"]["request_id"]
    weekly = _ok(client.post(H, headers=w["kitchen_auth"], json={"rule_type": "weekly", "weekdays": [6, 7]}))
    assert "Add: Closed every Saturday and Sunday" in db.query(AdminNotification).filter(
        AdminNotification.data["request_id"].astext == weekly["request"]["request_id"]).first().body
    mine = _ok(client.get(f"{API}/admin/notifications", headers=a1_hdr))
    assert mine["unread"] == 2 and mine["notifications"][0]["type"] == "holiday_request"
    _ok(client.put(f"{API}/admin/notifications/read-all", headers=a1_hdr))
    assert _ok(client.get(f"{API}/admin/notifications", headers=a1_hdr))["unread"] == 0
    listing = _ok(client.get(R, headers=a1_hdr, params={"status": "pending"}))
    assert listing["pending"] == 2 and {r["request_type"] for r in listing["requests"]} == {"emergency", "regular"}
    detail = _ok(client.get(f"{R}/{sent['request']['request_id']}", headers=a1_hdr))
    assert detail["request"]["impact_now"]["affected_orders"] == 1
    assert any(n["audience"] == "admin" and n["status"] == "sent" for n in detail["notices"])


def test_duplicate_requests_are_stored_once(client, db):
    w = f.world(db)
    first = _ok(client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": "2026-10-06"}))
    again = _ok(client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": "2026-10-06"}))
    assert again["duplicate"] is True and again["request"]["request_id"] == first["request"]["request_id"]
    weekly = _ok(client.post(H, headers=w["kitchen_auth"], json={"preset": "every_sunday"}))
    same = _ok(client.post(H, headers=w["kitchen_auth"], json={"rule_type": "weekly", "weekdays": [7]}))
    assert same["duplicate"] is True and same["request"]["request_id"] == weekly["request"]["request_id"]
    assert db.query(VendorHolidayRequest).count() == 2
    assert db.query(AdminNotification).count() == 0  # no admin yet: the notices wait in the log
    assert db.query(HolidayNotice).filter(HolidayNotice.audience == "admin").count() == 2
    # sent twice at the same moment: one row
    kitchen2, _ = f.provider(db)
    results = []

    def send():
        s = SessionLocal()
        try:
            results.append(HolidayRequestService.submit_emergency(s, kitchen2.provider_id, date(2026, 10, 7), None))
        finally:
            s.close()

    threads = [threading.Thread(target=send) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({r["request"]["request_id"] for r in results}) == 1
    assert sum(1 for r in results if not r["duplicate"]) == 1
    assert db.query(VendorHolidayRequest).filter(
        VendorHolidayRequest.provider_reference_id == kitchen2.provider_id).count() == 1


def test_withdrawn_and_expired_requests_change_nothing(client, db):
    w = f.world(db, balance="5000")
    _, admin_hdr = f.admin(db)
    sent = _ok(client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": "2026-10-06"}))
    out = _ok(client.delete(f"{H}/requests/{sent['request']['request_id']}", headers=w["kitchen_auth"]))
    assert out["request"]["status"] == "withdrawn"
    assert client.post(f"{R}/{sent['request']['request_id']}/approve", headers=admin_hdr, json={}).status_code == 409
    # an emergency nobody decided before its date expires
    late = _ok(client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": "2026-10-06"}))
    clock.freeze(datetime(2026, 10, 7, 9, 0))
    _, admin_hdr = f.admin(db)  # a fresh sign-in after the date
    r = client.post(f"{R}/{late['request']['request_id']}/approve", headers=admin_hdr, json={})
    assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_REQUEST_EXPIRED"
    db.expire_all()
    assert db.get(VendorHolidayRequest, uuid.UUID(late["request"]["request_id"])).status == "expired"
    kitchen_auth = f.auth(__import__("app.core.security", fromlist=["x"]).create_access_token(
        {"provider_id": str(w["kitchen"].provider_id)}, role="provider", token_version=0))
    other = _ok(client.post(f"{H}/emergency", headers=kitchen_auth, json={"date": "2026-10-08"}))
    clock.freeze(datetime(2026, 10, 9, 0, 30))
    jobs.holiday_retry_job()
    db.expire_all()
    assert db.get(VendorHolidayRequest, uuid.UUID(other["request"]["request_id"])).status == "expired"
    assert db.query(VendorHoliday).count() == 0
    assert db.query(ProviderNotification).filter(ProviderNotification.title == "Holiday request expired").count() == 2


def test_approving_twice_at_once_applies_the_change_once(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    admin, _ = f.admin(db)
    rid = _ok(f.ask_emergency(client, w["kitchen_auth"]))["request"]["request_id"]
    results, errors = [], []

    def approve():
        s = SessionLocal()
        try:
            results.append(HolidayRequestService.approve(s, uuid.UUID(rid), admin.admin_user_id))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            s.close()

    threads = [threading.Thread(target=approve) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert sum(1 for r in results if r.get("already_decided")) == 2
    db.expire_all()
    assert db.query(VendorHoliday).count() == 1
    assert db.query(SkipCreditTransaction).count() == 1
    assert db.query(WalletTransaction).filter(
        WalletTransaction.reason == "VENDOR_EMERGENCY_HOLIDAY_MEAL_REFUND").count() == 1
    assert _meals(db, sub_id)[0].status == "cancelled"


# ══ Emergency holiday ════════════════════════════════════════

def test_approved_emergency_refunds_skips_and_tells_everyone(client, db):
    w = f.world(db, balance="5000")
    boy, _ = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_a = _subscribe(client, w)                                   # lunch today
    b = _second_customer(db)
    sub_b = _subscribe(client, w, user_auth=b["user_auth"], address=b["address"], start="2026-10-06")  # no meal today
    c = _second_customer(db)
    sub_c = _subscribe(client, w, user_auth=c["user_auth"], address=c["address"], start="2026-10-06")
    _ok(client.put(f"{S}/{sub_c}/pause", headers=c["user_auth"]))  # paused, nothing due today: no gift skip
    assert db.get(Subscription, uuid.UUID(sub_c)).status == "paused"
    d = _second_customer(db, balance="1000")
    _ok(_extra_order(client, w, user_auth=d["user_auth"], address=d["address"]))
    extra = db.query(ExtraOrder).one()
    _ok(client.put(f"{API}/provider/orders/extra/{extra.extra_order_id}/status", headers=w["kitchen_auth"],
                   json={"status": "confirmed"}))
    before_a, before_d = _balance(db, w["user"]), _balance(db, d["user"])
    skips_c = db.get(Subscription, uuid.UUID(sub_c)).free_skips_total

    sent = _ok(f.ask_emergency(client, w["kitchen_auth"], reason="gas leak"))
    assert sent["request"]["impact"]["skip_credits"] == 2 and sent["request"]["impact"]["one_time_orders"] == 1
    _, admin_hdr = f.admin(db)
    out = _ok(client.post(f"{R}/{sent['request']['request_id']}/approve", headers=admin_hdr, json={"note": "Get well"}))
    assert out["request"]["status"] == "approved" and out["holiday"]["processing_status"] == "completed"
    assert out["request"]["result"]["refunded_meals"] == 1
    db.expire_all()

    # closed for that date only; no new orders, prep or pickups
    assert holidays.is_closed(db, w["kitchen"].provider_id, TODAY)
    assert not holidays.is_closed(db, w["kitchen"].provider_id, TODAY + timedelta(days=1))
    assert _extra_order(client, w, user_auth=b["user_auth"], address=b["address"]).json()["code"] == "KITCHEN_HOLIDAY"
    batch = _ok(client.get(f"{API}/provider/orders/next-batch", headers=w["kitchen_auth"]))["batch"]
    assert batch is None or batch["date"] != "2026-10-05"
    # meal refunded at its value; the rest of the plan unchanged
    meal_a = _meals(db, sub_a)[0]
    assert meal_a.order_date == TODAY and meal_a.status == "cancelled" and meal_a.refund_amount == Decimal("180.00")
    assert _balance(db, w["user"]) - before_a == Decimal("180.00")
    assert len(_meals(db, sub_a, "scheduled")) == 6
    # one-time order of the day cancelled and refunded in full
    extra = db.get(ExtraOrder, extra.extra_order_id)
    assert extra.status == "cancelled" and _balance(db, d["user"]) - before_d == extra.total_price
    # one extra free skip for every ACTIVE subscription, with or without a meal that day
    assert db.get(Subscription, uuid.UUID(sub_a)).free_skips_total == 3
    assert db.get(Subscription, uuid.UUID(sub_b)).free_skips_total == 3
    assert db.get(Subscription, uuid.UUID(sub_c)).free_skips_total == skips_c
    assert db.query(SkipCreditTransaction).count() == 2
    # customers told: closure, refund, wallet balance after it, the skip
    note_a = db.query(Notification).filter(Notification.user_reference_id == w["user"].user_id,
                                           Notification.type == "vendor_holiday_compensation").one()
    assert "on leave today due to an emergency, so food service will not be available" in note_a.body
    assert "₹180.00 for 1 meal" in note_a.body and f"₹{_balance(db, w['user']):.2f}" in note_a.body
    assert "1 extra free meal skip" in note_a.body and note_a.data["wallet_credit"] == "180.00"
    note_b = db.query(Notification).filter(Notification.user_reference_id == b["user"].user_id,
                                           Notification.type == "vendor_holiday_compensation").one()
    assert "nothing was charged" in note_b.body and "1 extra free meal skip" in note_b.body
    assert db.query(Notification).filter(Notification.user_reference_id == c["user"].user_id,
                                         Notification.type == "vendor_holiday_compensation").count() == 0
    note_d = db.query(Notification).filter(Notification.user_reference_id == d["user"].user_id,
                                           Notification.type == "order_cancelled").one()
    assert "refunded to your wallet" in note_d.body
    # the delivery partner: no pickup that day; the kitchen: approved
    boy_note = db.query(DeliveryBoyNotification).filter(
        DeliveryBoyNotification.delivery_boy_reference_id == boy.delivery_boy_id).all()
    assert any("No pickup is required" in n.body for n in boy_note)
    kitchen_note = db.query(ProviderNotification).filter(ProviderNotification.title == "Holiday request approved").one()
    assert "Get well" in kitchen_note.body
    # admin history: request, skips, refunds and notices
    detail = _ok(client.get(f"{API}/admin/holidays/{out['holiday']['holiday_id']}", headers=admin_hdr))
    assert detail["request"]["request_id"] == sent["request"]["request_id"]
    assert len(detail["skip_credits"]) == 2 and all(s["skip_status"] == "completed" for s in detail["skip_credits"])
    assert {n["audience"] for n in detail["notices"]} >= {"customer", "delivery_boy"}
    assert all(n["status"] == "sent" for n in detail["notices"])


def test_retries_never_refund_or_credit_twice(client, db):
    from app.domain import emergency_holiday

    w = f.world(db, balance="5000")
    _subscribe(client, w)
    _, admin_hdr = f.admin(db)
    rid = _ok(f.ask_emergency(client, w["kitchen_auth"]))["request"]["request_id"]
    hid = _ok(client.post(f"{R}/{rid}/approve", headers=admin_hdr, json={}))["holiday"]["holiday_id"]
    counts = lambda: (db.query(SkipCreditTransaction).count(), db.query(WalletTransaction).count(),  # noqa: E731
                      db.query(Notification).count(), db.query(HolidayNotice).count())
    first = counts()
    emergency_holiday.process(db, uuid.UUID(hid), retry_failed=True)
    emergency_holiday.retry_pending(db)
    _ok(client.post(f"{API}/admin/holidays/{hid}/retry", headers=admin_hdr))
    again = _ok(client.post(f"{R}/{rid}/approve", headers=admin_hdr, json={}))
    assert again["already_decided"] is True
    jobs.holiday_retry_job()
    db.expire_all()
    assert counts() == first
    row = db.query(VendorHolidaySubscription).one()
    assert row.refunded_meals == 1 and row.refund_amount == Decimal("180.00")


def test_a_failed_skip_is_retried_and_the_customer_told_only_after_it(client, db, monkeypatch):
    from app.domain import emergency_holiday

    w = f.world(db, balance="5000")
    _subscribe(client, w)
    real = emergency_holiday._grant_skip

    def broken(*args, **kwargs):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(emergency_holiday, "_grant_skip", broken)
    _, admin_hdr = f.admin(db)
    rid = _ok(f.ask_emergency(client, w["kitchen_auth"]))["request"]["request_id"]
    hid = _ok(client.post(f"{R}/{rid}/approve", headers=admin_hdr, json={}))["holiday"]["holiday_id"]
    db.expire_all()
    row = db.query(VendorHolidaySubscription).one()
    assert row.skip_status == "failed" and row.notice_queued_at is None
    assert db.query(Notification).filter(Notification.type == "vendor_holiday_compensation").count() == 0
    assert db.get(VendorHoliday, uuid.UUID(hid)).processing_status == "completed_with_errors"
    monkeypatch.setattr(emergency_holiday, "_grant_skip", real)
    _ok(client.post(f"{API}/admin/holidays/{hid}/retry", headers=admin_hdr))
    db.expire_all()
    assert db.query(SkipCreditTransaction).count() == 1
    assert db.query(Notification).filter(Notification.type == "vendor_holiday_compensation").count() == 1
    assert db.get(VendorHoliday, uuid.UUID(hid)).processing_status == "completed"


def test_failed_admin_notice_is_retried_from_the_log(client, db, monkeypatch):
    w = f.world(db)
    f.admin(db)
    real = holiday_notices._send

    def flaky(session, n):
        if n.audience == "admin":
            raise RuntimeError("mail down")
        return real(session, n)

    monkeypatch.setattr(holiday_notices, "_send", flaky)
    sent = _ok(f.ask_emergency(client, w["kitchen_auth"]))
    assert sent["request"]["status"] == "pending"  # the request is kept
    db.expire_all()
    assert db.query(HolidayNotice).one().status == "failed"
    monkeypatch.setattr(holiday_notices, "_send", real)
    jobs.holiday_retry_job()
    db.expire_all()
    assert db.query(HolidayNotice).one().status == "sent"
    assert db.query(AdminNotification).count() == 1


def test_emergency_on_a_day_already_closed_is_refused(client, db):
    w = f.world(db)
    f.planned_holiday(db, w["kitchen"], rule_type="dates", dates=["2026-10-07"])
    r = client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": "2026-10-07"})
    assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_EXISTS"
    # closed by another approved change while the request waited: approval refused, nothing applied twice
    sent = _ok(client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={"date": "2026-10-08"}))
    f.planned_holiday(db, w["kitchen"], rule_type="dates", dates=["2026-10-08"])
    _, admin_hdr = f.admin(db)
    r = client.post(f"{R}/{sent['request']['request_id']}/approve", headers=admin_hdr, json={})
    assert r.status_code == 409 and r.json()["code"] == "HOLIDAY_EXISTS"
    db.expire_all()
    assert db.get(VendorHolidayRequest, uuid.UUID(sent["request"]["request_id"])).status == "pending"
    assert db.query(VendorHoliday).filter(VendorHoliday.holiday_type == "emergency").count() == 0


# ══ Regular (weekly) holidays ════════════════════════════════

def test_kitchens_request_weekly_days_only(client, db):
    w = f.world(db)
    for body in ({"rule_type": "dates", "dates": ["2026-10-09"]}, {"date": "2026-10-09"},
                 {"rule_type": "range", "start_date": "2026-10-20", "end_date": "2026-10-22"},
                 {"rule_type": "monthly", "month_days": [1]}):
        r = client.post(H, headers=w["kitchen_auth"], json=body)
        assert r.status_code == 400 and r.json()["code"] == "HOLIDAY_WEEKLY_ONLY", body
    r = client.post(H, headers=w["kitchen_auth"], json={"rule_type": "weekly", "weekdays": [1, 2, 3, 4, 5, 6, 7]})
    assert r.status_code == 400


def test_weekly_holiday_add_change_remove_after_approval(client, db):
    w = f.world(db, balance="5000", plan_days=14)
    boy, _ = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _subscribe(client, w)
    b = _second_customer(db)
    sub_b = _subscribe(client, w, user_auth=b["user_auth"], address=b["address"], start="2026-10-12",
                       plan=f.plan(db, sub_type="three_day", days=3))  # Mon-Wed: no Sunday inside
    _ok(_extra_order(client, w, day=SUNDAY.isoformat()))
    balance = _balance(db, w["user"])

    # add every Sunday
    sent = _ok(client.post(H, headers=w["kitchen_auth"], json={"preset": "every_sunday"}))
    out = f.approve_holiday(client, db, sent)
    assert out["request"]["result"]["affected_subscriptions"] == 1
    db.expire_all()
    sub = db.get(Subscription, uuid.UUID(sub_id))
    assert sub.holiday_dates == ["2026-10-11", "2026-10-18"] and sub.end_date == date(2026, 10, 21)
    live = _meals(db, sub_id, "scheduled")
    assert len(live) == 14 and all(m.order_date.isoweekday() != 7 for m in live)
    assert db.query(ExtraOrder).one().status == "cancelled"  # the Sunday one-time order, refunded
    assert _balance(db, w["user"]) - balance == db.query(ExtraOrder).one().total_price
    told = db.query(Notification).filter(Notification.user_reference_id == w["user"].user_id,
                                         Notification.type == "vendor_holiday").one()
    assert "no charge" in told.body and "21 Oct 2026" not in told.body  # last meal is 20 Oct
    told_b = db.query(Notification).filter(Notification.user_reference_id == b["user"].user_id,
                                           Notification.type == "vendor_holiday").one()
    assert told_b.title.endswith("has new weekly days off") and "closed every sunday" in told_b.body.lower()
    assert db.get(Subscription, uuid.UUID(sub_b)).holiday_dates is None
    assert any("weekly days off" in n.title for n in db.query(DeliveryBoyNotification).filter(
        DeliveryBoyNotification.delivery_boy_reference_id == boy.delivery_boy_id))
    view = _ok(client.get(f"{API}/user/menu/packages", headers=w["user_auth"], params={"pin_code": f.PIN}))
    assert view["packages"][0]["vendor_holidays"]["weekly_off_label"] == "Weekly off: Sunday"
    rule_id = out["holiday"]["holiday_id"]

    # change to Saturday + Sunday
    change = _ok(client.put(f"{H}/rules/{rule_id}", headers=w["kitchen_auth"], json={"preset": "weekends"}))
    assert change["request"]["label"] == "Change: Closed every Sunday → Closed every Saturday and Sunday"
    conflict = client.put(f"{H}/rules/{rule_id}", headers=w["kitchen_auth"], json={"weekdays": [1], "rule_type": "weekly"})
    assert conflict.status_code == 409 and conflict.json()["code"] == "HOLIDAY_REQUEST_PENDING"
    assert client.delete(f"{H}/rules/{rule_id}", headers=w["kitchen_auth"]).status_code == 409
    assert not holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 10))  # pending
    changed = f.approve_holiday(client, db, change)
    db.expire_all()
    assert holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 10))
    live = _meals(db, sub_id, "scheduled")
    assert len(live) == 14 and all(m.order_date.isoweekday() < 6 for m in live)
    assert db.query(Notification).filter(Notification.user_reference_id == b["user"].user_id,
                                         Notification.title.like("%changed its weekly days off")).count() == 1

    # remove
    new_id = changed["holiday"]["holiday_id"]
    removal = _ok(client.delete(f"{H}/rules/{new_id}", headers=w["kitchen_auth"]))
    assert removal["request"]["action"] == "remove"
    f.approve_holiday(client, db, removal)
    db.expire_all()
    assert not holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 24))
    assert len(_meals(db, sub_id, "scheduled")) == 14  # no paid meal lost, nothing shortened
    assert db.query(Notification).filter(Notification.user_reference_id == b["user"].user_id,
                                         Notification.title.like("%removed a holiday")).count() == 1
    history = _ok(client.get(f"{H}/requests", headers=w["kitchen_auth"]))["requests"]
    assert [r["status"] for r in history] == ["approved"] * 3


@pytest.mark.parametrize("sub_type, days", [
    ("weekly", 7), ("monthly", 30), ("quarterly", 90), ("half_yearly", 180), ("annually", 365), ("custom", 0),
])
def test_weekly_holiday_keeps_every_purchased_meal_on_every_plan(client, db, sub_type, days):
    w = f.world(db, balance="100000")
    plan = w["plan"] if sub_type == "weekly" else f.plan(db, sub_type=sub_type, days=days)
    extra = {"end_date": "2026-10-25"} if sub_type == "custom" else {}
    sub_id = _subscribe(client, w, plan=plan, **extra)
    bought = len(_meals(db, sub_id, "scheduled"))
    paid = db.get(Subscription, uuid.UUID(sub_id)).final_amount
    assert bought == (21 if sub_type == "custom" else days)
    sent = _ok(client.post(H, headers=w["kitchen_auth"], json={"preset": "every_sunday"}))
    f.approve_holiday(client, db, sent)
    db.expire_all()
    sub = db.get(Subscription, uuid.UUID(sub_id))
    live = _meals(db, sub_id, "scheduled")
    # Sundays are not consumed meals: the same number of meals, none on a Sunday, the plan runs longer
    assert len(live) == bought and all(m.order_date.isoweekday() != 7 for m in live)
    assert sub.final_amount == paid and sub.status == "active"
    assert max(m.order_date for m in live) < sub.end_date
    sundays = [d for d in holidays.sub_holidays(sub) if d.isoweekday() == 7]
    assert len(sundays) >= 1


def test_a_plan_paused_from_tomorrow_still_gets_todays_meal_refunded_and_the_skip(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    _ok(client.put(f"{S}/{sub_id}/pause", headers=w["user_auth"]))
    db.expire_all()
    today = next(m for m in _meals(db, sub_id) if m.order_date == TODAY)
    if today.status != "scheduled":
        pytest.skip("the pause already covers today")
    before = _balance(db, w["user"])
    sent = _ok(f.ask_emergency(client, w["kitchen_auth"]))
    f.approve_holiday(client, db, sent)
    assert _balance(db, w["user"]) - before == Decimal("180.00")
    assert db.query(SkipCreditTransaction).count() == 1
    assert db.query(Notification).filter(Notification.type == "vendor_holiday_compensation").count() == 1


# ══ Part A on the server: price breakup layout, wallet, address ══

def test_breakup_sections_come_in_the_common_order_without_a_skip_price(client, db):
    w = f.world(db, balance="500", discount="5")
    q = _ok(client.post(f"{S}/quote", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "package_id": str(w["package"].package_id),
        "plan_id": str(w["plan"].subscription_plan_id), "address_id": str(w["address"].user_address_id),
        "start_date": "2026-10-05", "quantity": 1,
    }))
    b = q["price_breakup"]
    order = ["price", "adjustment", "discount", "wallet", "fees_taxes"]
    seen = [l["section"] for l in b["lines"]]
    assert seen == sorted(seen, key=order.index) and b["sections"] == order
    assert "skip" not in " ".join(l["key"] + " " + l["label"].lower() for l in b["lines"] if l["show"])
    wallet = next(l for l in b["lines"] if l["section"] == "wallet")
    assert wallet["amount"] == "-500.00"
    assert Decimal(b["total_payable"]) == Decimal(b["total"]) - Decimal("500.00")
    # the visible lines add up to what is left to pay, top to bottom
    shown = sum((Decimal(l["amount"]) for l in b["lines"] if l["in_total"] or l["section"] == "wallet"), Decimal(0))
    assert shown == Decimal(b["total_payable"])
    assert all(not l["show"] for l in b["lines"] if l["key"] in ("add_ons", "rounding") and l["amount"] == "0.00")


def test_switch_breakup_shows_the_credit_from_the_current_package(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    other = f.package(db, w["kitchen"], w["category"], price="200")
    r = _ok(client.post(f"{S}/{sub_id}/switch/preview", headers=w["user_auth"], json={
        "new_package_id": str(other.package_id), "old_package_id": str(w["package"].package_id),
    }))
    b = r["price_breakup"]
    credit = next(l for l in b["lines"] if l["key"] == "remaining_value")
    assert credit["section"] == "adjustment" and Decimal(credit["amount"]) < 0
    assert credit["label"] == "Credit from your current package (unused value)"
    sections = [l["section"] for l in b["lines"] if l["show"]]
    assert sections.index("adjustment") > sections.index("price")
    assert not next(l for l in b["lines"] if l["key"] == "difference")["show"]


def test_addresses_need_three_characters(client, db):
    f.pincode(db)
    _, _, hdr = f.customer(db)
    body = {"label": "Home", "address_line1": "12", "city": "Bengaluru", "state": "Karnataka", "pin_code": str(f.PIN)}
    assert client.post(f"{API}/user/address", headers=hdr, json=body).status_code == 422
    body["address_line1"] = "12A"
    assert client.post(f"{API}/user/address", headers=hdr, json=body).status_code in (200, 201)
