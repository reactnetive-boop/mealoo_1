"""
No pickup without the kitchen's "Ready for Pickup": the server enforces it
for every pickup path, whatever the apps show.
"""

import threading

from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from tests import factories as f

S = "/api/v1/user/subscription"
O = "/api/v1/user/order"
K = "/api/v1/provider/orders"
D = "/api/v1/delivery"
A = "/api/v1/admin"
NOT_READY = "Pickup is not allowed until the vendor marks the meal as Ready for Pickup."


def _setup(client, db):
    """Kitchen with its delivery partner, a 7-day lunch subscription from today."""
    w = f.world(db, balance="5000")
    boy, boy_hdr = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")
    assert client.post(f"{A}/delivery-boys/{boy.delivery_boy_id}/vendors", headers=admin_hdr,
                       json={"provider_id": str(w["kitchen"].provider_id)}).status_code == 200
    r = client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    db.expire_all()
    meals = (db.query(Order).filter(Order.subscription_reference_id == r.json()["subscription_id"])
             .order_by(Order.order_date).all())
    return w, boy, boy_hdr, r.json()["subscription_id"], meals


def _status(client, w, meal, status):
    return client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"], json={"status": status})


def _pickup(client, hdr, meal, code):
    return client.put(f"{D}/orders/{meal.order_id}/pickup", headers=hdr, json={"pickup_code": code})


def _ready_notes(db):
    db.expire_all()
    return db.query(DeliveryBoyNotification).filter(DeliveryBoyNotification.type == "order_ready").all()


def test_pickup_is_refused_until_the_kitchen_marks_ready(client, db):
    w, boy, boy_hdr, _, meals = _setup(client, db)
    meal = meals[0]
    code = f.pickup_code(db, w["kitchen"])

    for status in (None, "preparing"):  # scheduled, then preparing: both too early
        if status:
            assert _status(client, w, meal, status).status_code == 200
        r = _pickup(client, boy_hdr, meal, code)
        assert r.status_code == 409 and r.json()["code"] == "NOT_READY_FOR_PICKUP"
        assert r.json()["message"] == NOT_READY
        row = client.get(f"{D}/orders/{meal.order_id}", headers=boy_hdr).json()["order"]
        assert row["can_pickup"] is False and row["pickup_status"] in ("not_started", "preparing")
    db.expire_all()
    assert db.get(Order, meal.order_id).pickup_code_attempts == 0  # an early tap never burns a code attempt

    assert _status(client, w, meal, "ready_for_pickup").status_code == 200
    row = client.get(f"{D}/orders/{meal.order_id}", headers=boy_hdr).json()["order"]
    assert row["can_pickup"] is True and row["pickup_status"] == "ready"
    r = _pickup(client, boy_hdr, meal, code)
    assert r.status_code == 200 and r.json()["status"] == "picked_up"
    again = _pickup(client, boy_hdr, meal, code)
    assert again.status_code == 200 and again.json()["already_done"] is True


def test_kitchen_can_mark_ready_directly_but_only_eligible_meals_today(client, db):
    w, boy, boy_hdr, sub_id, meals = _setup(client, db)
    # straight from scheduled (no separate "preparing" step needed)
    assert _status(client, w, meals[0], "ready_for_pickup").status_code == 200

    # tomorrow's meal: not on its delivery date
    r = _status(client, w, meals[1], "ready_for_pickup")
    assert r.status_code == 400 and r.json()["code"] == "NOT_DELIVERY_DAY"

    # a skipped meal can never be made collectable
    assert client.put(f"{S}/{sub_id}/orders/{meals[2].order_id}/skip", headers=w["user_auth"]).status_code == 200
    r = _status(client, w, meals[2], "ready_for_pickup")
    assert r.status_code == 409 and r.json()["code"] == "NOT_ELIGIBLE_FOR_PICKUP" and "skipped" in r.json()["message"]

    # nor a cancelled one, nor another kitchen's
    meals[3].status = "cancelled"
    db.commit()
    r = _status(client, w, meals[3], "ready_for_pickup")
    assert r.status_code == 409 and r.json()["code"] == "NOT_ELIGIBLE_FOR_PICKUP"
    _, other_hdr = f.provider(db)
    assert client.put(f"{K}/subscription-orders/{meals[0].order_id}/status", headers=other_hdr,
                      json={"status": "ready_for_pickup"}).status_code == 404
    # partners and customers cannot mark anything ready
    assert client.put(f"{K}/subscription-orders/{meals[0].order_id}/status", headers=boy_hdr,
                      json={"status": "ready_for_pickup"}).status_code in (401, 403)


def test_ready_notice_goes_once_to_the_assigned_partner_only(client, db):
    w, boy, boy_hdr, sub_id, meals = _setup(client, db)
    other, _ = f.delivery_boy(db)
    first = _status(client, w, meals[0], "ready_for_pickup")
    assert first.status_code == 200 and first.json()["already_done"] is False
    repeat = _status(client, w, meals[0], "ready_for_pickup")
    assert repeat.status_code == 200 and repeat.json()["already_done"] is True

    notes = _ready_notes(db)
    assert len(notes) == 1 and notes[0].delivery_boy_reference_id == boy.delivery_boy_id
    n = notes[0]
    assert w["package"].package_name in n.body and "lunch" in n.body and "MG Road" in n.body
    assert n.data["order_id"] == str(meals[0].order_id) and n.data["subscription_id"] == sub_id
    assert n.data["package_names"] == [w["package"].package_name] and n.data["meal_slot"] == "lunch"
    assert "MG Road" in n.data["pickup_address"]
    assert not db.query(DeliveryBoyNotification).filter(
        DeliveryBoyNotification.delivery_boy_reference_id == other.delivery_boy_id,
        DeliveryBoyNotification.type == "order_ready",
    ).count()


def test_only_the_assigned_partner_can_pick_up(client, db):
    w, boy, boy_hdr, _, meals = _setup(client, db)
    stranger, stranger_hdr = f.delivery_boy(db)
    assert _status(client, w, meals[0], "ready_for_pickup").status_code == 200
    code = f.pickup_code(db, w["kitchen"])
    assert _pickup(client, stranger_hdr, meals[0], code).status_code == 404
    bulk = client.post(f"{D}/pickups/bulk", headers=stranger_hdr,
                       json={"provider_id": str(w["kitchen"].provider_id), "pickup_code": code})
    assert bulk.status_code == 404 and bulk.json()["code"] == "NOTHING_READY"
    db.expire_all()
    assert db.get(Order, meals[0].order_id).status == "ready_for_pickup"


def test_simultaneous_pickups_hand_over_once(client, db, app):
    from fastapi.testclient import TestClient

    w, boy, boy_hdr, _, meals = _setup(client, db)
    assert _status(client, w, meals[0], "ready_for_pickup").status_code == 200
    code = f.pickup_code(db, w["kitchen"])
    results = []

    def go():
        with TestClient(app) as c:
            results.append(_pickup(c, boy_hdr, meals[0], code).json())

    threads = [threading.Thread(target=go) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for r in results if r.get("success") and not r.get("already_done")) == 1
    assert all(r.get("success") for r in results)
    db.expire_all()
    assert db.get(Order, meals[0].order_id).status == "picked_up"


def test_one_time_checkout_is_ready_as_one_trip(client, db):
    w, boy, boy_hdr, _, _ = _setup(client, db)
    second = f.package(db, w["kitchen"], w["category"])
    placed = client.post(f"{O}/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-05", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1},
                  {"package_id": str(second.package_id), "quantity": 1}],
    }).json()
    first_id, second_id = (line["extra_order_id"] for line in placed["orders"])
    for line_id in (first_id, second_id):
        assert client.put(f"{K}/extra/{line_id}/status", headers=w["kitchen_auth"], json={"status": "confirmed"}).status_code == 200
    code = f.pickup_code(db, w["kitchen"])
    r = client.put(f"{D}/extra-orders/{first_id}/pickup", headers=boy_hdr, json={"pickup_code": code})
    assert r.status_code == 409 and r.json()["code"] == "NOT_READY_FOR_PICKUP"

    ready = client.put(f"{K}/extra/{first_id}/status", headers=w["kitchen_auth"], json={"status": "ready_for_pickup"})
    assert ready.status_code == 200 and ready.json()["also_updated"] == [second_id]
    assert len(_ready_notes(db)) == 1  # one trip, one notice

    r = client.put(f"{D}/extra-orders/{first_id}/pickup", headers=boy_hdr, json={"pickup_code": code})
    assert r.status_code == 200 and r.json()["also_updated"] == [second_id]
    db.expire_all()
    assert {o.status for o in db.query(ExtraOrder).all()} == {"picked_up"}


def test_bulk_pickup_collects_only_ready_meals(client, db):
    w, boy, boy_hdr, _, meals = _setup(client, db)
    assert _status(client, w, meals[0], "preparing").status_code == 200
    code = f.pickup_code(db, w["kitchen"])
    body = {"provider_id": str(w["kitchen"].provider_id), "pickup_code": code}
    r = client.post(f"{D}/pickups/bulk", headers=boy_hdr, json=body)
    assert r.status_code == 404 and r.json()["code"] == "NOTHING_READY"
    db.expire_all()
    assert db.get(Order, meals[0].order_id).status == "preparing"

    assert _status(client, w, meals[0], "ready_for_pickup").status_code == 200
    r = client.post(f"{D}/pickups/bulk", headers=boy_hdr, json=body)
    assert r.status_code == 200 and [p["order_id"] for p in r.json()["picked_up"]] == [str(meals[0].order_id)]
