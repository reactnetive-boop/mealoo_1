"""Complaints from all three apps: one admin list, one resolution flow, notifications back."""

from app.models.audit_log_model import AuditLog
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.notification_model import Notification
from app.models.provider_notification_model import ProviderNotification
from tests import factories as f

A = "/api/v1/admin/complaints"
BODY = {"against": "platform", "subject": "App problem", "description": "Something is not working right."}


def _raise_all(client, db):
    user, _, user_hdr = f.customer(db)
    kitchen, kitchen_hdr = f.provider(db)
    boy, boy_hdr = f.delivery_boy(db, kitchen=kitchen)
    ids = {}
    for name, path, hdr in (
        ("user", "/api/v1/user/complaint", user_hdr),
        ("provider", "/api/v1/provider/complaint", kitchen_hdr),
        ("delivery_boy", "/api/v1/delivery/complaint", boy_hdr),
    ):
        r = client.post(path, headers=hdr, json=BODY)
        assert r.status_code in (200, 201), r.text
    _, admin_hdr = f.admin(db)
    listed = client.get(A, headers=admin_hdr).json()["complaints"]
    for row in listed:
        ids[row["complainant_type"]] = row["id"]
    return user, kitchen, boy, admin_hdr, ids


def test_admin_list_combines_pages_and_filters(client, db):
    _, _, _, admin_hdr, ids = _raise_all(client, db)
    assert set(ids) == {"user", "provider", "delivery_boy"}

    r = client.get(A, headers=admin_hdr, params={"limit": 2}).json()
    assert r["total"] == 3 and len(r["complaints"]) == 2
    page2 = client.get(A, headers=admin_hdr, params={"limit": 2, "page": 2}).json()["complaints"]
    assert len(page2) == 1
    assert {c["id"] for c in r["complaints"] + page2} == set(ids.values())

    only_kitchen = client.get(A, headers=admin_hdr, params={"complaint_type": "provider"}).json()
    assert only_kitchen["total"] == 1 and only_kitchen["complaints"][0]["complainant_type"] == "provider"
    assert client.get(A, headers=admin_hdr, params={"status": "resolved"}).json()["total"] == 0
    assert client.get(A, headers=admin_hdr, params={"complaint_type": "alien"}).status_code == 400


def test_resolution_notifies_whoever_raised_it(client, db):
    user, kitchen, boy, admin_hdr, ids = _raise_all(client, db)
    for name, path in (("user", "user"), ("provider", "provider"), ("delivery_boy", "delivery-boy")):
        r = client.put(f"{A}/{path}/{ids[name]}/resolve", headers=admin_hdr,
                       json={"status": "resolved", "resolution": "Fixed in the latest update."})
        assert r.status_code == 200, r.text
        detail = client.get(f"{A}/{path}/{ids[name]}", headers=admin_hdr).json()
        assert detail["status"] == "resolved" and detail["resolved_at"]
        # a closed complaint cannot be resolved again
        again = client.put(f"{A}/{path}/{ids[name]}/resolve", headers=admin_hdr, json={"status": "closed"})
        assert again.status_code == 400

    db.expire_all()
    assert db.query(Notification).filter(Notification.user_reference_id == user.user_id).count() == 1
    assert db.query(ProviderNotification).filter(
        ProviderNotification.provider_reference_id == kitchen.provider_id).count() == 1
    assert db.query(DeliveryBoyNotification).filter(
        DeliveryBoyNotification.delivery_boy_reference_id == boy.delivery_boy_id).count() == 1
    assert db.query(AuditLog).filter(AuditLog.table_name.like("%complaints")).count() == 3


def test_resolution_rejects_bad_status_and_unknown_ids(client, db):
    _, _, _, admin_hdr, ids = _raise_all(client, db)
    bad = client.put(f"{A}/user/{ids['user']}/resolve", headers=admin_hdr, json={"status": "deleted"})
    assert bad.status_code in (400, 422)
    missing = client.put(f"{A}/user/{ids['provider']}/resolve", headers=admin_hdr, json={"status": "resolved"})
    assert missing.status_code == 404
    assert client.get(f"{A}/provider/{ids['user']}", headers=admin_hdr).status_code == 404


def test_customer_can_complain_about_one_subscription_meal(client, db):
    from app.models.complaint_model import Complaint
    from app.models.order_model import Order

    w = f.world(db)
    r = client.post("/api/v1/user/subscription", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    sub_id = r.json()["subscription_id"]
    meal = db.query(Order).filter(Order.subscription_reference_id == sub_id).first()
    body = {**BODY, "against": "vendor", "subscription_order_id": str(meal.order_id)}
    r = client.post("/api/v1/user/complaint", headers=w["user_auth"], json=body)
    assert r.status_code in (200, 201), r.text
    row = db.query(Complaint).one()
    assert row.subscription_order_reference_id == meal.order_id
    assert str(row.subscription_reference_id) == sub_id and row.vendor_reference_id == w["kitchen"].provider_id

    # someone else's meal is invisible
    _, _, stranger = f.customer(db)
    assert client.post("/api/v1/user/complaint", headers=stranger, json=body).status_code == 404


def test_complaint_sla_assignment_and_ageing(client, db):
    from datetime import datetime

    from app.core import clock

    _, _, _, admin_hdr, ids = _raise_all(client, db)
    me = client.get("/api/v1/admin/auth/profile", headers=admin_hdr).json()["admin"]["admin_user_id"]
    listed = client.get(A, headers=admin_hdr).json()
    assert listed["sla_hours"] == 24 and all(c["overdue"] is False for c in listed["complaints"])

    r = client.put(f"{A}/provider/{ids['provider']}/assign", headers=admin_hdr, json={"admin_id": me})
    assert r.status_code == 200, r.text
    mine = client.get(A, headers=admin_hdr, params={"assigned_to": "me"}).json()
    assert [c["id"] for c in mine["complaints"]] == [ids["provider"]]
    assert client.get(A, headers=admin_hdr, params={"assigned_to": "unassigned"}).json()["total"] == 2

    # rows get the database's now(); pin them to the frozen "today" so ageing does not depend on the real date
    from app.models.complaint_model import Complaint
    from app.models.delivery_boy_complaint_model import DeliveryBoyComplaint
    from app.models.provider_complaint_model import ProviderComplaint
    for model in (Complaint, ProviderComplaint, DeliveryBoyComplaint):
        db.query(model).update({model.created_at: clock.now_utc()}, synchronize_session=False)
    db.commit()
    clock.freeze(datetime(2026, 10, 7, 5, 0))  # two days later (a new admin session)
    _, admin_hdr = f.admin(db)
    late = client.get(A, headers=admin_hdr, params={"overdue": True}).json()
    assert late["total"] == 3 and all(c["overdue"] for c in late["complaints"])

    # acting on a complaint makes you its owner
    client.put(f"{A}/user/{ids['user']}/resolve", headers=admin_hdr, json={"status": "in_progress"})
    assert client.get(A, headers=admin_hdr, params={"assigned_to": "me"}).json()["total"] == 1
