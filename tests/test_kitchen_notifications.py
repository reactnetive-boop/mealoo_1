"""Kitchen in-app notifications: what creates them and who can read them."""

from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from tests import factories as f

N = "/api/v1/provider/notifications"
K = "/api/v1/provider/orders"
A = "/api/v1/admin/orders"


def _subscribe(client, w):
    r = client.post("/api/v1/user/subscription", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def _types(client, hdr):
    return [n["type"] for n in client.get(N, headers=hdr).json()["notifications"]]


def test_new_subscription_and_one_time_order_reach_the_kitchen(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    r = client.post("/api/v1/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-06", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 2}],
    })
    assert r.status_code == 200, r.text

    body = client.get(N, headers=w["kitchen_auth"]).json()
    assert body["unread"] == 2
    by_type = {n["type"]: n for n in body["notifications"]}
    assert by_type["new_subscription"]["data"]["subscription_id"] == sub_id
    assert "please confirm" in by_type["new_order"]["title"]
    assert db.query(ExtraOrder).count() == 1


def test_assignment_changes_and_unstaffed_pickups_reach_the_kitchen(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    boy, _ = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")

    meal = db.query(Order).filter(Order.subscription_reference_id == sub_id).order_by(Order.order_date).first()
    hdr = w["kitchen_auth"]
    client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=hdr, json={"status": "preparing"})
    client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=hdr, json={"status": "ready_for_pickup"})
    assert "pickup_pending" in _types(client, hdr)

    assert client.put(f"{A}/subscriptions/{sub_id}/assign-delivery-boy", headers=admin_hdr,
                      json={"delivery_boy_id": str(boy.delivery_boy_id)}).status_code == 200
    assert client.put(f"{A}/subscriptions/{sub_id}/unassign-delivery-boy", headers=admin_hdr,
                      json={"reason": "partner on leave"}).status_code == 200
    types = _types(client, hdr)
    assert "partner_assigned" in types and "partner_unassigned" in types


def test_kitchens_only_see_and_mark_their_own_notifications(client, db):
    w = f.world(db, balance="5000")
    _subscribe(client, w)
    other_kitchen, other_hdr = f.provider(db)
    _, boy_auth = f.delivery_boy(db)

    mine = client.get(N, headers=w["kitchen_auth"]).json()["notifications"]
    assert len(mine) == 1
    assert client.get(N, headers=other_hdr).json()["total"] == 0
    assert client.put(f"{N}/{mine[0]['provider_notification_id']}/read", headers=other_hdr).status_code == 404
    assert client.get(N, headers=boy_auth).status_code == 403

    assert client.put(f"{N}/{mine[0]['provider_notification_id']}/read", headers=w["kitchen_auth"]).status_code == 200
    assert client.get(N, headers=w["kitchen_auth"]).json()["unread"] == 0
    assert client.put(f"{N}/read-all", headers=w["kitchen_auth"]).status_code == 200
