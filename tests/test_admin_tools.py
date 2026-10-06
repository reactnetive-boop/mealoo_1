"""AD-06 / AD-07: audit log viewer, categories, admin accounts, broadcast, partner wallet."""

from decimal import Decimal

from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.notification_model import Notification
from app.models.provider_notification_model import ProviderNotification
from tests import factories as f

A = "/api/v1/admin"


def test_audit_log_search_is_super_admin_only(client, db):
    _, super_hdr = f.admin(db)
    _, mod_hdr = f.admin(db, role="moderator")
    client.post(f"{A}/categories", headers=super_hdr, json={"category_name": "South Indian"})
    assert client.get(f"{A}/audit-logs", headers=mod_hdr).status_code == 403
    r = client.get(f"{A}/audit-logs", headers=super_hdr, params={"table": "master.menu_categories"}).json()
    assert r["total"] == 1 and r["logs"][0]["operation"] == "I" and r["logs"][0]["actor_name"]
    tables = client.get(f"{A}/audit-logs/tables", headers=super_hdr).json()["tables"]
    assert {"table": "master.menu_categories", "entries": 1} in tables


def test_categories_crud_and_guard(client, db):
    _, hdr = f.admin(db)
    created = client.post(f"{A}/categories", headers=hdr, json={"category_name": "North Indian", "display_order": 2})
    assert created.status_code == 200, created.text
    cat = created.json()["category"]
    assert cat["category_slug"] == "north-indian"
    assert client.post(f"{A}/categories", headers=hdr, json={"category_name": "North Indian"}).status_code == 409

    kitchen, _ = f.provider(db)
    used = f.category(db)
    f.package(db, kitchen, used)
    r = client.put(f"{A}/categories/{used.category_id}", headers=hdr, json={"is_active": False})
    assert r.status_code == 400  # packages still use it
    r = client.put(f"{A}/categories/{cat['category_id']}", headers=hdr, json={"is_active": False})
    assert r.status_code == 200 and r.json()["category"]["is_active"] is False
    listed = client.get(f"{A}/categories", headers=hdr).json()["categories"]
    assert {c["category_name"] for c in listed} >= {"North Indian"}


def test_admin_accounts(client, db):
    me, hdr = f.admin(db)
    r = client.post(f"{A}/admins", headers=hdr, json={
        "full_name": "Ops Person", "email": "ops@orleeno.test", "password": "Strong-pass-1", "role": "moderator",
    })
    assert r.status_code == 200, r.text
    new_id = r.json()["admin"]["admin_user_id"]
    assert client.post("/api/v1/admin/auth/login", json={"email": "ops@orleeno.test", "password": "Strong-pass-1"}).status_code == 200
    assert client.put(f"{A}/admins/{new_id}", headers=hdr, json={"is_active": False}).status_code == 200
    assert client.post("/api/v1/admin/auth/login", json={"email": "ops@orleeno.test", "password": "Strong-pass-1"}).status_code == 403
    # the last super admin cannot lock everyone out
    assert client.put(f"{A}/admins/{me.admin_user_id}", headers=hdr, json={"role": "moderator"}).status_code == 400


def test_broadcast_reaches_each_audience(client, db):
    _, hdr = f.admin(db)
    f.customer(db)
    f.customer(db, status="blocked")
    f.provider(db)
    f.delivery_boy(db)
    r = client.post(f"{A}/notifications/broadcast", headers=hdr, json={
        "audience": "everyone", "title": "Diwali hours", "body": "Kitchens close early on Diwali.",
    })
    assert r.status_code == 200, r.text
    assert r.json()["recipients"] == {"customers": 1, "kitchens": 1, "partners": 1}
    assert db.query(Notification).filter(Notification.type == "announcement").count() == 1
    assert db.query(ProviderNotification).count() == 1 and db.query(DeliveryBoyNotification).count() == 1


def test_partner_wallet_adjustment_is_idempotent(client, db):
    _, hdr = f.admin(db)
    boy, _ = f.delivery_boy(db)
    url = f"{A}/delivery-boys/{boy.delivery_boy_id}/wallet/adjust"
    body = {"amount": "50", "type": "credit", "reason": "Fuel bonus"}
    first = client.post(url, headers={**hdr, "Idempotency-Key": "fuel-1"}, json=body)
    again = client.post(url, headers={**hdr, "Idempotency-Key": "fuel-1"}, json=body)
    assert first.status_code == again.status_code == 200
    assert Decimal(str(again.json()["balance_after"])) == Decimal("50.00")
    debit = client.post(url, headers=hdr, json={"amount": "80", "type": "debit", "reason": "Too much"})
    assert debit.status_code == 400 and debit.json()["code"] == "INSUFFICIENT_BALANCE"
