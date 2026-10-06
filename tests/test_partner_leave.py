"""BE-B11: a partner's day off moves their deliveries instead of silently failing them."""

from datetime import date

from app.models.order_model import Order
from app.models.provider_notification_model import ProviderNotification
from tests import factories as f

S = "/api/v1/user/subscription"
L = "/api/v1/delivery/leaves"


def _assigned_subscription(client, db):
    w = f.world(db)
    boy, boy_hdr = f.delivery_boy(db, kitchen=w["kitchen"])
    _, admin_hdr = f.admin(db)
    sub_id = client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    }).json()["subscription_id"]
    r = client.put(f"/api/v1/admin/orders/subscriptions/{sub_id}/assign-delivery-boy", headers=admin_hdr,
                   json={"delivery_boy_id": str(boy.delivery_boy_id)})
    assert r.status_code == 200, r.text
    return w, boy, boy_hdr, admin_hdr, sub_id


def _holder(db, sub_id, day):
    db.expire_all()
    return db.query(Order).filter(Order.subscription_reference_id == sub_id, Order.order_date == day).one().delivery_boy_reference_id


def test_leave_releases_that_day_and_cancel_brings_it_back(client, db):
    w, boy, boy_hdr, _, sub_id = _assigned_subscription(client, db)
    day = date(2026, 10, 7)
    assert _holder(db, sub_id, day) == boy.delivery_boy_id

    r = client.post(L, headers=boy_hdr, json={"leave_date": "2026-10-07", "reason": "Family function"})
    assert r.status_code == 200 and r.json()["released_orders"] == 1
    assert _holder(db, sub_id, day) is None
    assert _holder(db, sub_id, date(2026, 10, 8)) == boy.delivery_boy_id
    assert db.query(ProviderNotification).filter(ProviderNotification.title == "Delivery partner on leave").count() == 1

    # nobody can hand them that day's order meanwhile
    meal = db.query(Order).filter(Order.subscription_reference_id == sub_id, Order.order_date == day).one()
    r = client.put(f"/api/v1/provider/orders/subscription-orders/{meal.order_id}/assign-delivery-boy",
                   headers=w["kitchen_auth"], json={"delivery_boy_id": str(boy.delivery_boy_id)})
    assert r.status_code in (400, 404)

    assert client.get(L, headers=boy_hdr).json()["leaves"][0]["leave_date"] == "2026-10-07"
    r = client.delete(f"{L}/2026-10-07", headers=boy_hdr)
    assert r.status_code == 200 and r.json()["restored_meals"] == 1
    assert _holder(db, sub_id, day) == boy.delivery_boy_id


def test_reassignment_skips_leave_days(client, db):
    w, boy, boy_hdr, admin_hdr, sub_id = _assigned_subscription(client, db)
    other, _ = f.delivery_boy(db, kitchen=w["kitchen"])
    client.post(f"/api/v1/admin/delivery-boys/{other.delivery_boy_id}/leaves", headers=admin_hdr,
                json={"leave_date": "2026-10-08"})
    r = client.put(f"/api/v1/admin/orders/subscriptions/{sub_id}/assign-delivery-boy", headers=admin_hdr,
                   json={"delivery_boy_id": str(other.delivery_boy_id)})
    assert r.status_code == 200, r.text
    assert r.json()["skipped"]["partner_on_leave"] == 1
    assert _holder(db, sub_id, date(2026, 10, 8)) == boy.delivery_boy_id  # stays with the previous partner
    assert _holder(db, sub_id, date(2026, 10, 9)) == other.delivery_boy_id


def test_leave_rules(client, db):
    _, boy_hdr = f.delivery_boy(db)
    assert client.post(L, headers=boy_hdr, json={"leave_date": "2026-10-04"}).status_code == 400   # past
    assert client.post(L, headers=boy_hdr, json={"leave_date": "2027-03-01"}).status_code == 400   # too far
    assert client.post(L, headers=boy_hdr, json={"leave_date": "2026-10-10"}).status_code == 200
    assert client.post(L, headers=boy_hdr, json={"leave_date": "2026-10-10"}).status_code == 409
    assert client.delete(f"{L}/2026-10-11", headers=boy_hdr).status_code == 404


def test_kitchen_sees_customer_and_partner_names_on_subscriptions(client, db):
    w, boy, _, _, sub_id = _assigned_subscription(client, db)
    kitchen = w["kitchen_auth"]
    listed = client.get("/api/v1/provider/orders/subscriptions", headers=kitchen).json()["subscriptions"]
    assert listed[0]["customer_name"] == w["user"].full_name.split()[0]
    assert listed[0]["delivery_boy_name"] == boy.full_name
    assert listed[0]["packages"][0]["package_name"] == w["package"].package_name
    detail = client.get(f"/api/v1/provider/orders/subscriptions/{sub_id}", headers=kitchen).json()
    assert detail["subscription"]["delivery_area"]
    meal = detail["orders"][0]
    assert meal["customer_name"] and meal["delivery_boy_name"] == boy.full_name and meal["packages"]
    # the kitchen never gets the customer's phone or delivery code
    assert "phone" not in str(detail) and "delivery_code" not in str(detail)
