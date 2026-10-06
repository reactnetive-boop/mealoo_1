"""
Subscription delivery assignment, kitchen daily pickup codes, customer
delivery codes: rules, permissions, audit, attempt limits and concurrency.
"""

import threading
from datetime import date, datetime, timedelta

from app.core import clock
from app.core.clock import today_local
from app.models.audit_log_model import AuditLog
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.notification_model import Notification
from app.models.order_model import Order
from app.models.provider_pickup_code_model import ProviderPickupCode
from app.models.subscription_delivery_assignment_model import SubscriptionDeliveryAssignment
from app.models.subscription_model import Subscription
from app.schedulers import jobs
from tests import factories as f

A = "/api/v1/admin/orders"
D = "/api/v1/delivery"
K = "/api/v1/provider/orders"
S = "/api/v1/user/subscription"


def _subscribe(client, w, start="2026-10-05"):
    r = client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id),
        "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id),
        "start_date": start,
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def _meals(db, sub_id):
    db.expire_all()
    return (
        db.query(Order)
        .filter(Order.subscription_reference_id == sub_id)
        .order_by(Order.order_date.asc())
        .all()
    )


def _assign(client, admin_hdr, sub_id, boy, note=None):
    return client.put(f"{A}/subscriptions/{sub_id}/assign-delivery-boy", headers=admin_hdr,
                      json={"delivery_boy_id": str(boy.delivery_boy_id), "note": note})


def _setup(client, db):
    """Kitchen + 7-day lunch subscription starting today + approved pool partner + admin."""
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    boy, boy_auth = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")
    return w, sub_id, boy, boy_auth, admin_hdr


def _second_kitchen_subscription(client, db, w):
    """Another kitchen in the same pincode with its own customer and subscription."""
    kitchen, kitchen_auth = f.provider(db)
    pkg = f.package(db, kitchen, w["category"])
    user, address, user_auth = f.customer(db, balance="5000")
    w2 = {**w, "kitchen": kitchen, "kitchen_auth": kitchen_auth, "package": pkg, "user": user,
          "address": address, "user_auth": user_auth}
    return w2, _subscribe(client, w2)


def _ready_meal(client, db, w, sub_id, boy, admin_hdr):
    """Assign the subscription and let the kitchen start today's meal."""
    assert _assign(client, admin_hdr, sub_id, boy).status_code == 200
    meal = _meals(db, sub_id)[0]
    r = client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"], json={"status": "preparing"})
    assert r.status_code == 200, r.text
    return meal


# ── Subscription assignment ───────────────────────────────────

def test_admin_assigns_every_open_meal_of_a_subscription(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    r = _assign(client, admin_hdr, sub_id, boy, note="morning route")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["subscription_id"] == sub_id
    assert body["delivery_boy_id"] == str(boy.delivery_boy_id)
    assert body["assigned_orders"] == 7 and body["newly_assigned"] == 7 and body["action"] == "assigned"

    meals = _meals(db, sub_id)
    assert all(m.delivery_boy_reference_id == boy.delivery_boy_id for m in meals)
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert sub.delivery_boy_reference_id == boy.delivery_boy_id
    rows = db.query(SubscriptionDeliveryAssignment).all()
    assert len(rows) == 1 and rows[0].status == "active" and rows[0].orders_assigned == 7 and rows[0].note == "morning route"
    assert db.query(DeliveryBoyNotification).filter(
        DeliveryBoyNotification.delivery_boy_reference_id == boy.delivery_boy_id,
        DeliveryBoyNotification.type == "subscription_assigned",
    ).count() == 1
    audit = db.query(AuditLog).filter(AuditLog.table_name == "subscription.subscriptions").all()
    assert any(a.new_data.get("event") == "subscription_delivery_assigned" for a in audit)

    # repeating the same assignment changes nothing and is safe
    again = _assign(client, admin_hdr, sub_id, boy).json()
    assert again["action"] == "unchanged" and again["already_assigned"] == 7
    assert db.query(SubscriptionDeliveryAssignment).count() == 1


def test_cancelled_completed_and_picked_up_meals_are_not_reassigned(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    first, _ = f.delivery_boy(db)
    meals = _meals(db, sub_id)
    meals[0].status, meals[0].delivery_boy_reference_id = "picked_up", first.delivery_boy_id
    meals[1].status, meals[1].delivery_boy_reference_id = "delivered", first.delivery_boy_id
    meals[2].status = "cancelled"
    meals[3].status = "skipped"
    db.commit()

    body = _assign(client, admin_hdr, sub_id, boy).json()
    assert body["assigned_orders"] == 3
    assert body["skipped"] == {"in_progress": 1, "delivered": 1, "skipped": 1, "cancelled": 1, "past": 0,
                               "partner_on_leave": 0}
    assert body["total_orders"] == 7

    meals = _meals(db, sub_id)
    assert meals[0].delivery_boy_reference_id == first.delivery_boy_id  # still carrying it
    assert meals[1].delivery_boy_reference_id == first.delivery_boy_id  # history untouched
    assert meals[2].delivery_boy_reference_id is None
    assert meals[3].delivery_boy_reference_id is None
    assert all(m.delivery_boy_reference_id == boy.delivery_boy_id for m in meals[4:])


def test_reassignment_moves_open_meals_and_keeps_history(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    other, other_auth = f.delivery_boy(db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    # today's meal is picked up by the first partner before the change
    code = f.pickup_code(db, w["kitchen"])
    assert client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code}).status_code == 200

    body = _assign(client, admin_hdr, sub_id, other).json()
    assert body["action"] == "reassigned"
    assert body["reassigned_from_other_partner"] == 6 and body["skipped"]["in_progress"] == 1
    meals = _meals(db, sub_id)
    assert meals[0].delivery_boy_reference_id == boy.delivery_boy_id
    assert all(m.delivery_boy_reference_id == other.delivery_boy_id for m in meals[1:])

    history = db.query(SubscriptionDeliveryAssignment).order_by(SubscriptionDeliveryAssignment.assigned_at).all()
    assert [h.status for h in history] == ["ended", "active"]
    assert history[0].end_reason == "reassigned" and history[0].delivery_boy_reference_id == boy.delivery_boy_id
    assert db.query(DeliveryBoyNotification).filter(
        DeliveryBoyNotification.delivery_boy_reference_id == boy.delivery_boy_id,
        DeliveryBoyNotification.type == "subscription_unassigned",
    ).count() == 1
    # the first partner can still finish the meal they carry, but no longer sees the subscription
    assert client.get(f"{D}/subscriptions/{sub_id}", headers=boy_auth).status_code == 404
    r = client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": f.delivery_code(meal)})
    assert r.status_code == 200, r.text


def test_new_meals_inherit_the_subscription_partner(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    assert _assign(client, admin_hdr, sub_id, boy).status_code == 200
    # meals regenerated by the midnight job (here: after removing the later ones)
    db.query(Order).filter(Order.subscription_reference_id == sub_id, Order.order_date > date(2026, 10, 7)).delete()
    db.commit()
    jobs.generate_meals_job()
    meals = _meals(db, sub_id)
    assert len(meals) == 7
    assert all(m.delivery_boy_reference_id == boy.delivery_boy_id for m in meals)


def test_meals_restored_on_resume_follow_a_reassignment_made_while_paused(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    other, _ = f.delivery_boy(db)
    assert _assign(client, admin_hdr, sub_id, boy).status_code == 200
    assert client.put(f"{S}/{sub_id}/pause", headers=w["user_auth"]).status_code == 200
    body = _assign(client, admin_hdr, sub_id, other).json()  # paused subscriptions can be assigned
    assert body["skipped"]["cancelled"] == 6  # paused meals are not assigned
    clock.freeze(datetime(2026, 10, 6, 5, 0))
    assert client.put(f"{S}/{sub_id}/resume", headers=w["user_auth"]).status_code == 200
    future = [m for m in _meals(db, sub_id) if m.status == "scheduled"]
    assert future and all(m.delivery_boy_reference_id == other.delivery_boy_id for m in future)


def test_only_admins_can_assign(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    for hdr in (w["kitchen_auth"], boy_auth, w["user_auth"]):
        assert _assign(client, hdr, sub_id, boy).status_code in (401, 403)
        assert client.get(f"{A}/subscriptions/{sub_id}", headers=hdr).status_code in (401, 403)
    assert client.put(f"{A}/subscriptions/{sub_id}/assign-delivery-boy",
                      json={"delivery_boy_id": str(boy.delivery_boy_id)}).status_code in (401, 403)
    assert db.query(SubscriptionDeliveryAssignment).count() == 0


def test_invalid_partner_or_subscription_is_rejected(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    pending, _ = f.delivery_boy(db, approved=False)
    r = _assign(client, admin_hdr, sub_id, pending)
    assert r.status_code == 400 and r.json()["code"] == "PARTNER_NOT_ELIGIBLE"

    inactive, _ = f.delivery_boy(db)
    inactive.is_active = False
    db.commit()
    assert _assign(client, admin_hdr, sub_id, inactive).status_code == 400

    other_kitchen, _ = f.provider(db)
    dedicated, _ = f.delivery_boy(db, kitchen=other_kitchen)
    r = _assign(client, admin_hdr, sub_id, dedicated)
    assert r.status_code == 400 and "another kitchen" in r.json()["message"]

    r = client.put(f"{A}/subscriptions/{sub_id}/assign-delivery-boy", headers=admin_hdr,
                   json={"delivery_boy_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 404
    r = client.put(f"{A}/subscriptions/00000000-0000-0000-0000-000000000000/assign-delivery-boy", headers=admin_hdr,
                   json={"delivery_boy_id": str(boy.delivery_boy_id)})
    assert r.status_code == 404

    assert client.put(f"{S}/{sub_id}/cancel", headers=w["user_auth"], json={}).status_code == 200
    r = _assign(client, admin_hdr, sub_id, boy)
    assert r.status_code == 409 and r.json()["code"] == "SUBSCRIPTION_NOT_ASSIGNABLE"
    assert all(m.delivery_boy_reference_id is None for m in _meals(db, sub_id))


def test_unassign_releases_open_meals(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    assert _assign(client, admin_hdr, sub_id, boy).status_code == 200
    r = client.put(f"{A}/subscriptions/{sub_id}/unassign-delivery-boy", headers=admin_hdr, json={"reason": "partner on leave"})
    assert r.status_code == 200, r.text
    assert r.json()["released_orders"] == 7
    assert all(m.delivery_boy_reference_id is None for m in _meals(db, sub_id))
    assert db.query(SubscriptionDeliveryAssignment).one().end_reason == "unassigned"
    again = client.put(f"{A}/subscriptions/{sub_id}/unassign-delivery-boy", headers=admin_hdr, json={"reason": "again"})
    assert again.status_code == 409


def test_deactivating_a_partner_ends_their_subscription_assignments(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    _, super_hdr = f.admin(db)
    assert _assign(client, admin_hdr, sub_id, boy).status_code == 200
    r = client.put(f"/api/v1/admin/delivery-boys/{boy.delivery_boy_id}", headers=super_hdr, json={"is_active": False})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Subscription).filter(Subscription.subscription_id == sub_id).one().delivery_boy_reference_id is None
    assert db.query(SubscriptionDeliveryAssignment).one().end_reason == "partner_deactivated"
    assert all(m.delivery_boy_reference_id is None for m in _meals(db, sub_id))


def test_kitchen_cannot_change_an_assignment(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    other, _ = f.delivery_boy(db)
    r = client.put(f"{K}/subscription-orders/{meal.order_id}/assign-delivery-boy", headers=w["kitchen_auth"],
                   json={"delivery_boy_id": str(other.delivery_boy_id)})
    assert r.status_code == 409 and r.json()["code"] == "PARTNER_ALREADY_ASSIGNED"
    assert _meals(db, sub_id)[0].delivery_boy_reference_id == boy.delivery_boy_id


def test_admin_subscription_detail_counts(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meals = _meals(db, sub_id)
    meals[1].status = "cancelled"
    db.commit()
    assert _assign(client, admin_hdr, sub_id, boy).status_code == 200
    d = client.get(f"{A}/subscriptions/{sub_id}", headers=admin_hdr).json()
    assert d["delivery_boy"]["delivery_boy_id"] == str(boy.delivery_boy_id)
    assert d["assignment_status"] == "assigned"
    assert d["stats"]["total"] == 7 and d["stats"]["pending"] == 6 and d["stats"]["cancelled"] == 1
    assert d["stats"]["assigned_to_current"] == 6
    assert d["customer"]["full_name"] and d["provider"]["business_name"] and d["plan"]["duration_days"] == 7
    assert len(d["assignment_history"]) == 1 and len(d["orders"]) == 7

    listed = client.get(f"{A}/subscriptions", headers=admin_hdr, params={"assignment": "assigned"}).json()
    assert listed["total"] == 1 and listed["subscriptions"][0]["delivery_boy_name"] == boy.full_name
    assert client.get(f"{A}/subscriptions", headers=admin_hdr, params={"assignment": "unassigned"}).json()["total"] == 0


# ── Partner views ─────────────────────────────────────────────

def test_partner_sees_only_their_own_subscriptions(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    other, other_auth = f.delivery_boy(db)
    assert _assign(client, admin_hdr, sub_id, boy).status_code == 200

    mine = client.get(f"{D}/subscriptions", headers=boy_auth).json()
    assert mine["total"] == 1
    row = mine["subscriptions"][0]
    assert row["today_orders"] == 1 and row["pending_orders"] == 7 and row["customer_name"] and row["vendor_name"]
    assert row["next_order"]["date"] == "2026-10-05"

    detail = client.get(f"{D}/subscriptions/{sub_id}", headers=boy_auth).json()
    groups = [o["group"] for o in detail["orders"]]
    assert groups.count("today") == 1 and groups.count("upcoming") == 6
    assert detail["orders"][0]["is_next"] is True

    assert client.get(f"{D}/subscriptions", headers=other_auth).json()["total"] == 0
    assert client.get(f"{D}/subscriptions/{sub_id}", headers=other_auth).status_code == 404
    assert client.get(f"{D}/orders/{detail['orders'][0]['order_id']}", headers=other_auth).status_code == 404


def test_dashboard_shows_counts_active_and_next(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    board = client.get(f"{D}/dashboard", headers=boy_auth).json()
    assert board["counts"]["total"] == 0 and board["next_delivery"] is None

    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    board = client.get(f"{D}/dashboard", headers=boy_auth).json()
    assert board["counts"]["total"] == 1 and board["counts"]["pending"] == 1
    assert board["next_delivery"]["order_id"] == str(meal.order_id) and board["active_delivery"] is None
    assert board["assigned_subscriptions"] == 1

    code = f.pickup_code(db, w["kitchen"])
    client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code})
    board = client.get(f"{D}/dashboard", headers=boy_auth).json()
    assert board["counts"]["picked_up"] == 1 and board["counts"]["pending"] == 0
    assert board["active_delivery"]["order_id"] == str(meal.order_id)
    # the next delivery is tomorrow's meal
    assert board["next_delivery"]["date"] == "2026-10-06"
    assert code not in str(board) and f.delivery_code(meal) not in str(board)


# ── Kitchen pickup code ───────────────────────────────────────

def test_kitchen_sees_its_daily_code_and_nobody_else_does(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    r = client.get("/api/v1/provider/pickup-code", headers=w["kitchen_auth"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["pickup_code"]) == 6 and body["code_date"] == "2026-10-05"
    assert body["orders_awaiting_pickup"] == 1
    # same code all day, stored only as a seed
    assert client.get("/api/v1/provider/pickup-code", headers=w["kitchen_auth"]).json()["pickup_code"] == body["pickup_code"]
    row = db.query(ProviderPickupCode).one()
    assert body["pickup_code"] not in (row.code_seed or "")

    other_kitchen, other_hdr = f.provider(db)
    assert client.get("/api/v1/provider/pickup-code", headers=other_hdr).json()["pickup_code"] != body["pickup_code"]
    for hdr in (boy_auth, w["user_auth"], admin_hdr):
        assert client.get("/api/v1/provider/pickup-code", headers=hdr).status_code in (401, 403)
    assert db.query(AuditLog).filter(AuditLog.table_name == "provider.provider_pickup_codes").count() >= 1


def test_daily_job_generates_codes_for_kitchens_with_orders(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    f.provider(db)  # a kitchen without orders today gets no code
    jobs.pickup_codes_job()
    rows = db.query(ProviderPickupCode).all()
    assert len(rows) == 1 and rows[0].provider_reference_id == w["kitchen"].provider_id


# ── Pickup verification ───────────────────────────────────────

def test_correct_pickup_code_picks_up_and_is_audited(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    code = f.pickup_code(db, w["kitchen"])
    r = client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "picked_up" and r.json()["already_done"] is False
    meal = _meals(db, sub_id)[0]
    assert meal.status == "picked_up" and meal.picked_up_at is not None

    audit = [a for a in db.query(AuditLog).filter(AuditLog.table_name == "subscription.orders").all()
             if (a.new_data or {}).get("event") == "pickup_verification"]
    assert [a.new_data["result"] for a in audit] == ["success"]
    assert audit[0].changed_by == boy.delivery_boy_id and audit[0].changed_by_type == "delivery_boy"
    assert code not in str([a.new_data for a in db.query(AuditLog).all()])


def test_wrong_expired_or_other_kitchen_codes_fail(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    code = f.pickup_code(db, w["kitchen"])
    url = f"{D}/orders/{meal.order_id}/pickup"

    r = client.put(url, headers=boy_auth, json={"pickup_code": f.wrong_code(code)})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_PICKUP_CODE"
    assert "ask the kitchen for today's pickup code" in r.json()["message"]

    yesterday = f.pickup_code(db, w["kitchen"], today_local() - timedelta(days=1))
    if yesterday != code:
        assert client.put(url, headers=boy_auth, json={"pickup_code": yesterday}).status_code == 400

    other_kitchen, _ = f.provider(db)
    other_code = f.pickup_code(db, other_kitchen)
    if other_code != code:
        assert client.put(url, headers=boy_auth, json={"pickup_code": other_code}).status_code == 400

    # a revoked code stops working even when typed correctly
    row = db.query(ProviderPickupCode).filter(
        ProviderPickupCode.provider_reference_id == w["kitchen"].provider_id,
        ProviderPickupCode.code_date == today_local(),
    ).one()
    row.status = "revoked"
    db.commit()
    assert client.put(url, headers=boy_auth, json={"pickup_code": code}).status_code == 400
    assert _meals(db, sub_id)[0].status == "preparing"
    assert _meals(db, sub_id)[0].pickup_code_attempts >= 2

    # malformed codes never reach the check
    assert client.put(url, headers=boy_auth, json={"pickup_code": "1234"}).status_code == 422


def test_regenerated_code_replaces_the_old_one(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    old = client.get("/api/v1/provider/pickup-code", headers=w["kitchen_auth"]).json()["pickup_code"]
    new = client.post("/api/v1/provider/pickup-code/regenerate", headers=w["kitchen_auth"]).json()
    assert new["version"] == 2
    if new["pickup_code"] != old:
        assert client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": old}).status_code == 400
    assert client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth,
                      json={"pickup_code": new["pickup_code"]}).status_code == 200


def test_pickup_needs_a_started_meal_and_the_assigned_partner(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    assert _assign(client, admin_hdr, sub_id, boy).status_code == 200
    meal = _meals(db, sub_id)[0]
    code = f.pickup_code(db, w["kitchen"])
    r = client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code})
    assert r.status_code == 400 and r.json()["code"] == "NOT_READY_FOR_PICKUP"

    client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"], json={"status": "preparing"})
    client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"], json={"status": "ready_for_pickup"})
    assert db.query(DeliveryBoyNotification).filter(DeliveryBoyNotification.type == "order_ready").count() == 1

    # another partner gets nothing, even with the right code
    other, other_auth = f.delivery_boy(db)
    assert client.put(f"{D}/orders/{meal.order_id}/pickup", headers=other_auth, json={"pickup_code": code}).status_code == 404
    assert client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code}).status_code == 200

    # already picked up: nothing changes, no second success is recorded
    again = client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code})
    assert again.status_code == 200 and again.json()["already_done"] is True
    successes = [a for a in db.query(AuditLog).all()
                 if (a.new_data or {}).get("event") == "pickup_verification" and a.new_data.get("result") == "success"]
    assert len(successes) == 1


def test_pickup_attempts_are_limited_per_order_and_per_day(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    code = f.pickup_code(db, w["kitchen"])
    url = f"{D}/orders/{meal.order_id}/pickup"
    for _ in range(5):
        assert client.put(url, headers=boy_auth, json={"pickup_code": f.wrong_code(code)}).status_code == 400
    r = client.put(url, headers=boy_auth, json={"pickup_code": code})
    assert r.status_code == 423 and r.json()["code"] == "PICKUP_LOCKED"

    # support unlocks after checking
    r = client.put(f"{A}/subscription-orders/{meal.order_id}/reset-verification", headers=admin_hdr,
                   json={"pickup": True, "delivery": False, "reason": "checked with kitchen"})
    assert r.status_code == 200, r.text
    assert client.put(url, headers=boy_auth, json={"pickup_code": code}).status_code == 200


def test_daily_pickup_failure_limit_blocks_guessing_across_orders(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    code = f.pickup_code(db, w["kitchen"])
    # the partner already guessed two other orders of today into their lock (5 + 4, then one more)
    locked = []
    for attempts in (5, 4):
        extra, sub2 = _second_kitchen_subscription(client, db, w)
        assert _assign(client, admin_hdr, sub2, boy).status_code == 200
        m2 = _meals(db, sub2)[0]
        client.put(f"{K}/subscription-orders/{m2.order_id}/status", headers=extra["kitchen_auth"], json={"status": "preparing"})
        db.expire_all()
        m2 = _meals(db, sub2)[0]
        m2.pickup_code_attempts = attempts
        db.commit()
        locked.append((m2, f.pickup_code(db, extra["kitchen"])))
    m2, other_code = locked[1]
    assert client.put(f"{D}/orders/{m2.order_id}/pickup", headers=boy_auth,
                      json={"pickup_code": f.wrong_code(other_code)}).status_code == 400
    # 10 failures today: even the right code for a fresh order is refused now
    assert _meals(db, sub_id)[0].pickup_code_attempts == 0
    r = client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code})
    assert r.status_code == 429 and r.json()["code"] == "PICKUP_VERIFICATION_BLOCKED"


def test_concurrent_pickups_record_one_hand_over(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    code = f.pickup_code(db, w["kitchen"])
    results = []

    def go():
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            r = c.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code})
            results.append((r.status_code, r.json().get("already_done")))

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert {s for s, _ in results} == {200}
    assert sorted(done for _, done in results) == [False, True, True, True]
    db.expire_all()
    successes = [a for a in db.query(AuditLog).all()
                 if (a.new_data or {}).get("event") == "pickup_verification" and a.new_data.get("result") == "success"]
    assert len(successes) == 1


def test_concurrent_assignments_leave_one_active_partner(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    other, _ = f.delivery_boy(db)
    codes = []

    def go(partner):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            codes.append(c.put(f"{A}/subscriptions/{sub_id}/assign-delivery-boy", headers=admin_hdr,
                               json={"delivery_boy_id": str(partner.delivery_boy_id)}).status_code)

    threads = [threading.Thread(target=go, args=(p,)) for p in (boy, other, boy, other)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert set(codes) == {200}
    db.expire_all()
    active = db.query(SubscriptionDeliveryAssignment).filter(SubscriptionDeliveryAssignment.status == "active").all()
    assert len(active) == 1
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert sub.delivery_boy_reference_id == active[0].delivery_boy_reference_id
    assert {m.delivery_boy_reference_id for m in _meals(db, sub_id)} == {sub.delivery_boy_reference_id}


# ── Delivery verification ─────────────────────────────────────

def _picked_up(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    code = f.pickup_code(db, w["kitchen"])
    assert client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth, json={"pickup_code": code}).status_code == 200
    return w, sub_id, boy, boy_auth, admin_hdr, meal


def test_start_delivery_and_arrival_notify_the_customer(client, db):
    w, sub_id, boy, boy_auth, admin_hdr, meal = _picked_up(client, db)
    assert client.put(f"{D}/orders/{meal.order_id}/start-delivery", headers=boy_auth).json()["status"] == "out_for_delivery"
    assert client.put(f"{D}/orders/{meal.order_id}/arrived", headers=boy_auth).status_code == 200
    assert client.put(f"{D}/orders/{meal.order_id}/arrived", headers=boy_auth).json()["already_done"] is True
    titles = [n.title for n in db.query(Notification).filter(Notification.user_reference_id == w["user"].user_id)]
    assert "Out for delivery" in titles and titles.count("Your delivery partner is here") == 1


def test_correct_delivery_code_delivers_once(client, db):
    w, sub_id, boy, boy_auth, admin_hdr, meal = _picked_up(client, db)
    url = f"{D}/orders/{meal.order_id}/deliver"
    r = client.put(url, headers=boy_auth, json={"otp": f.delivery_code(meal)})
    assert r.status_code == 200 and r.json()["status"] == "delivered"
    again = client.put(url, headers=boy_auth, json={"otp": f.delivery_code(meal)})
    assert again.status_code == 200 and again.json()["already_done"] is True
    events = [a.new_data for a in db.query(AuditLog).all() if (a.new_data or {}).get("event") == "delivery_verification"]
    assert [e["result"] for e in events] == ["success"]
    assert f.delivery_code(meal) not in str(events)


def test_wrong_expired_or_other_order_delivery_codes_fail(client, db):
    w, sub_id, boy, boy_auth, admin_hdr, meal = _picked_up(client, db)
    url = f"{D}/orders/{meal.order_id}/deliver"
    code = f.delivery_code(meal)

    r = client.put(url, headers=boy_auth, json={"otp": f.wrong_code(code)})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_DELIVERY_CODE"
    assert "ask the customer" in r.json()["message"]

    tomorrow = _meals(db, sub_id)[1]
    if f.delivery_code(tomorrow) != code:
        assert client.put(url, headers=boy_auth, json={"otp": f.delivery_code(tomorrow)}).status_code == 400

    other, other_auth = f.delivery_boy(db)
    assert client.put(url, headers=other_auth, json={"otp": code}).status_code == 404

    # the code stops working a few hours after the delivery day
    clock.freeze(datetime(2026, 10, 6, 3, 30))
    r = client.put(url, headers=boy_auth, json={"otp": code})
    assert r.status_code == 400 and r.json()["code"] == "DELIVERY_CODE_EXPIRED"
    assert _meals(db, sub_id)[0].status == "picked_up"


def test_delivery_needs_pickup_first(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _ready_meal(client, db, w, sub_id, boy, admin_hdr)
    r = client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": f.delivery_code(meal)})
    assert r.status_code == 400 and r.json()["code"] == "NOT_PICKED_UP"


# ── Customer delivery code ────────────────────────────────────

def test_customer_sees_only_their_own_code_on_the_day(client, db):
    w, sub_id, boy, boy_auth, admin_hdr = _setup(client, db)
    meal = _meals(db, sub_id)[0]
    today = client.get("/api/v1/user/order/today", headers=w["user_auth"]).json()
    assert today["total"] == 1 and today["deliveries"][0]["delivery_code"] == f.delivery_code(meal)
    assert today["deliveries"][0]["vendor_name"] == w["kitchen"].business_name

    _, _, stranger_auth = f.customer(db)
    assert client.get("/api/v1/user/order/today", headers=stranger_auth).json()["total"] == 0
    assert client.get(f"{S}/{sub_id}/orders", headers=stranger_auth).status_code == 404

    # partner and kitchen never receive it
    _assign(client, admin_hdr, sub_id, boy)
    assert f.delivery_code(meal) not in client.get(f"{D}/orders/{meal.order_id}", headers=boy_auth).text
    assert f.delivery_code(meal) not in client.get(f"{K}/subscription-orders", headers=w["kitchen_auth"]).text


def test_bulk_pickup_collects_everything_ready_with_one_code(client, db):
    from app.models.extra_order_model import ExtraOrder

    w = f.world(db, balance="5000")
    boy, boy_hdr = f.delivery_boy(db, kitchen=w["kitchen"])
    _, admin_hdr = f.admin(db)
    sub_id = _subscribe(client, w)
    _assign(client, admin_hdr, sub_id, boy)
    r = client.post("/api/v1/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-05", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    extra = db.query(ExtraOrder).one()
    K = "/api/v1/provider/orders"
    for status in ("confirmed", "preparing", "ready_for_pickup"):
        client.put(f"{K}/extra/{extra.extra_order_id}/status", headers=w["kitchen_auth"], json={"status": status})
    client.put(f"{K}/extra/{extra.extra_order_id}/assign-delivery-boy", headers=w["kitchen_auth"],
               json={"delivery_boy_id": str(boy.delivery_boy_id)})
    meal = _meals(db, sub_id)[0]
    for status in ("preparing", "ready_for_pickup"):
        client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"], json={"status": status})

    url = "/api/v1/delivery/pickups/bulk"
    code = f.pickup_code(db, w["kitchen"])
    bad = client.post(url, headers=boy_hdr, json={"provider_id": str(w["kitchen"].provider_id), "pickup_code": f.wrong_code(code)})
    assert bad.status_code == 400 and bad.json()["code"] == "INVALID_PICKUP_CODE"
    r = client.post(url, headers=boy_hdr, json={"provider_id": str(w["kitchen"].provider_id), "pickup_code": code})
    assert r.status_code == 200, r.text
    assert {p["kind"] for p in r.json()["picked_up"]} == {"subscription", "extra"}
    again = client.post(url, headers=boy_hdr, json={"provider_id": str(w["kitchen"].provider_id), "pickup_code": code})
    assert again.status_code == 404 and again.json()["code"] == "NOTHING_READY"
