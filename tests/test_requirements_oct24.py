"""
Mealoo requirements of 2026-10-24 (Mealoo_Requirements.md, points 1-12),
through the API the four apps call.
"""

import io
import json
import uuid
from datetime import datetime
from decimal import Decimal

import httpx
from PIL import Image

from app.core import clock, push
from app.core.clock import today_local
from app.domain import payout_audit
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.delivery_boy_wallet_transaction_model import DeliveryBoyWalletTransaction
from app.models.delivery_partner_vendor_model import DeliveryPartnerVendor
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.provider_notification_model import ProviderNotification
from app.models.subscription_model import Subscription
from app.schedulers import jobs
from tests import factories as f

M = "/api/v1/user/menu"
S = "/api/v1/user/subscription"
O = "/api/v1/user/order"
R = "/api/v1/user/review"
K = "/api/v1/provider/orders"
P = "/api/v1/provider"
D = "/api/v1/delivery"
A = "/api/v1/admin"

PIN_MESSAGE = "Delivery is not available at this PIN code. Please change your PIN code."


# ── helpers ───────────────────────────────────────────────────

def _subscribe(client, w, plan=None, start="2026-10-05", package=None, kitchen=None, user_auth=None, address=None):
    r = client.post(S, headers=user_auth or w["user_auth"], json={
        "vendor_id": str((kitchen or w["kitchen"]).provider_id),
        "plan_id": str((plan or w["plan"]).subscription_plan_id),
        "address_id": str((address or w["address"]).user_address_id),
        "start_date": start,
        "items": [{"package_id": str((package or w["package"]).package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def _meals(db, sub_id):
    db.expire_all()
    return (
        db.query(Order).filter(Order.subscription_reference_id == sub_id)
        .order_by(Order.order_date.asc(), Order.meal_slot.asc()).all()
    )


def _extra(client, w, *, day="2026-10-05", slot="lunch", items=None, user_auth=None, address=None, kitchen=None):
    return client.post(f"{O}/extra", headers=user_auth or w["user_auth"], json={
        "vendor_id": str((kitchen or w["kitchen"]).provider_id),
        "address_id": str((address or w["address"]).user_address_id),
        "delivery_date": day,
        "meal_slot": slot,
        "items": items or [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })


def _give_kitchen(client, admin_hdr, boy, kitchen, note=None):
    return client.post(f"{A}/delivery-boys/{boy.delivery_boy_id}/vendors", headers=admin_hdr,
                       json={"provider_id": str(kitchen.provider_id), "note": note})


def _deliver_meal(client, db, kitchen_auth, kitchen, meal, boy_auth):
    oid = str(meal.order_id)
    r = client.put(f"{K}/subscription-orders/{oid}/status", headers=kitchen_auth, json={"status": "preparing"})
    assert r.status_code == 200, r.text
    r = client.put(f"{D}/orders/{oid}/pickup", headers=boy_auth, json={"pickup_code": f.pickup_code(db, kitchen)})
    assert r.status_code == 200, r.text
    return client.put(f"{D}/orders/{oid}/deliver", headers=boy_auth, json={"otp": f.delivery_code(meal)})


def _wallet(db, boy):
    db.expire_all()
    w = db.query(DeliveryBoyWallet).filter(DeliveryBoyWallet.delivery_boy_reference_id == boy.delivery_boy_id).first()
    return w.balance if w else Decimal("0.00")


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 160, 90)).save(out, "PNG")
    return out.getvalue()


# ── Point 1: prices on the home / signup screens ──────────────

def test_lowest_prices_come_from_what_is_on_sale_in_the_pincode(client, db):
    w = f.world(db, price="200", discounted="150", sub_price="140")
    f.plan(db, sub_type="monthly", slot="lunch", days=30, discount="5")
    cheap = f.package(db, w["kitchen"], w["category"], price="120", sub_available=False)

    r = client.get(f"{M}/serviceability", headers=w["user_auth"], params={"pin_code": f.PIN})
    assert r.status_code == 200, r.text
    summary = r.json()["offer_summary"]
    assert summary["lowest_one_time_price"] == "120.00"
    assert summary["lowest_one_time_package"]["package_id"] == str(cheap.package_id)
    assert summary["lowest_subscription_meal_price"] == "140.00"
    assert summary["subscription_discount_percent"] == "5.00"
    plan = summary["starting_plan"]
    assert plan["subscription_type"] == "monthly" and plan["meals"] == 30
    assert (plan["original_amount"], plan["discount_amount"], plan["final_amount"]) == ("4200.00", "210.00", "3990.00")

    listing = client.get(f"{M}/packages", headers=w["user_auth"], params={"pin_code": f.PIN}).json()
    assert listing["offer_summary"]["lowest_one_time_price"] == "120.00"


def test_no_prices_or_offers_where_nothing_is_sold(client, db):
    f.pincode(db)
    f.pincode(db, pin=560002)  # Orleeno serves it, no kitchen does
    _, _, hdr = f.customer(db)
    served_empty = client.get(f"{M}/serviceability", headers=hdr, params={"pin_code": 560002}).json()
    assert served_empty["status"] == "no_kitchens" and served_empty["offer_summary"] is None
    outside = client.get(f"{M}/serviceability", headers=hdr, params={"pin_code": 110092}).json()
    assert outside["serviceable"] is False and outside["offer_summary"] is None
    listing = client.get(f"{M}/packages", headers=hdr, params={"pin_code": 110092}).json()
    assert listing["packages"] == [] and listing["offer_summary"] is None


# ── Point 2: package photos shared by kitchen and admin ───────

def test_kitchen_photo_shows_in_admin_and_admin_can_manage_it(client, db):
    w = f.world(db)
    _, admin_hdr = f.admin(db, role="moderator")
    pkg = w["package"]
    up = client.post("/api/v1/package/image/upload", headers=w["kitchen_auth"], params={"package_id": str(pkg.package_id)},
                     files={"file": ("thali.png", io.BytesIO(_png()), "image/png")})
    assert up.status_code == 200, up.text
    kitchen_url = up.json()["image_url"]

    detail = client.get(f"{A}/packages/{pkg.package_id}", headers=admin_hdr).json()
    assert detail["image_url"] == kitchen_url and detail["images"][0]["image_url"] == kitchen_url
    row = next(p for p in client.get(f"{A}/packages", headers=admin_hdr).json()["packages"] if p["package_id"] == str(pkg.package_id))
    assert row["image_url"] == kitchen_url and row["image_count"] == 1

    added = client.post(f"{A}/packages/{pkg.package_id}/images", headers=admin_hdr, data={"make_primary": "true"},
                        files={"file": ("new.png", io.BytesIO(_png()), "image/png")})
    assert added.status_code == 200, added.text
    new_id = added.json()["image"]["image_id"]
    assert added.json()["images"][0]["image_id"] == new_id and added.json()["images"][0]["is_primary"]

    replaced = client.put(f"{A}/packages/{pkg.package_id}/images/{new_id}", headers=admin_hdr,
                          files={"file": ("v2.png", io.BytesIO(_png()), "image/png")})
    assert replaced.status_code == 200, replaced.text
    new_url = replaced.json()["image"]["image_url"]
    assert new_url != added.json()["image"]["image_url"]

    # the kitchen sees exactly what the admin set
    mine = client.get(f"/api/v1/menu/get/{pkg.package_id}", headers=w["kitchen_auth"]).json()
    assert mine["image_url"] == new_url and len(mine["images"]) == 2
    assert db.query(ProviderNotification).filter(ProviderNotification.type == "package_update").count() >= 2

    old_id = next(i["image_id"] for i in replaced.json()["images"] if i["image_id"] != new_id)
    assert client.put(f"{A}/packages/{pkg.package_id}/images/{old_id}/primary", headers=admin_hdr).status_code == 200
    gone = client.delete(f"{A}/packages/{pkg.package_id}/images/{old_id}", headers=admin_hdr)
    assert gone.status_code == 200 and [i["is_primary"] for i in gone.json()["images"]] == [True]
    # a kitchen token cannot use the admin photo endpoints
    assert client.delete(f"{A}/packages/{pkg.package_id}/images/{new_id}", headers=w["kitchen_auth"]).status_code in (401, 403)


# ── Point 3: 5% off the whole subscription bill ───────────────

def test_plan_discount_is_taken_once_off_the_total(client, db):
    w = f.world(db, price="250", balance="6000", plan_days=20, discount="5")
    q = client.post(f"{S}/quote", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "package_id": str(w["package"].package_id),
        "plan_id": str(w["plan"].subscription_plan_id), "address_id": str(w["address"].user_address_id),
        "start_date": "2026-10-05", "quantity": 1,
    })
    assert q.status_code == 200, q.text
    b = q.json()["breakdown"]
    assert (b["base_amount"], b["discount_percent"], b["discount_amount"], b["total_payable"]) == (
        "5000.00", "5.00", "250.00", "4750.00")

    sub_id = _subscribe(client, w)
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert (sub.total_amount, sub.discount_amount, sub.final_amount) == (Decimal("5000.00"), Decimal("250.00"), Decimal("4750.00"))
    # every meal is still priced at 250; the discount is not taken per meal
    assert all(Decimal(str(sp.unit_price)) == Decimal("250.00") for sp in sub.packages)
    kitchen_view = client.get(f"{K}/subscriptions/{sub_id}", headers=w["kitchen_auth"]).json()["subscription"]
    assert kitchen_view["discount_percent"] == "5.00" and "pricing_snapshot" not in kitchen_view
    _, admin_hdr = f.admin(db, role="moderator")
    admin_view = client.get(f"{A}/orders/subscriptions/{sub_id}", headers=admin_hdr).json()["subscription"]
    assert Decimal(str(admin_view["discount_percent"])) == Decimal("5")
    assert Decimal(str(admin_view["final_amount"])) == Decimal("4750")


# ── Point 4: several meals together ───────────────────────────

def test_any_meal_combination_is_priced_on_the_server(client, db):
    w = f.world(db, price="100", meal_type="breakfast,lunch,dinner", balance="5000", discount="5")
    pair = f.plan(db, sub_type="weekly", slot="lunch_dinner", days=7, discount="5")
    f.plan(db, sub_type="weekly", slot="all_slots", days=7, discount="5")
    params = {"package_id": str(w["package"].package_id), "provider_id": str(w["kitchen"].provider_id)}

    r = client.get(f"{S}/plans", headers=w["user_auth"], params={**params, "meal_slots": "dinner,lunch"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meal_slot"] == "lunch_dinner" and body["meal_slots"] == ["lunch", "dinner"]
    pricing = body["plans"][0]["pricing"]
    assert (pricing["meals"], pricing["original_amount"], pricing["discount_amount"], pricing["total_payable"]) == (
        14, "1400.00", "70.00", "1330.00")

    three = client.get(f"{S}/plans", headers=w["user_auth"], params={**params, "meal_slots": "breakfast,lunch,dinner"}).json()
    assert three["meal_slot"] == "all_slots" and three["plans"][0]["pricing"]["meals"] == 21

    sub_id = _subscribe(client, w, plan=pair)
    meals = _meals(db, sub_id)
    assert len(meals) == 14 and {m.meal_slot for m in meals} == {"lunch", "dinner"}
    assert client.get(f"{S}/{sub_id}", headers=w["user_auth"]).json()["meal_slots"] == ["lunch", "dinner"]
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert sub.final_amount == Decimal("1330.00")

    lunch_only = f.package(db, w["kitchen"], w["category"], meal_type="lunch")
    bad = client.get(f"{S}/plans", headers=w["user_auth"], params={
        "package_id": str(lunch_only.package_id), "provider_id": str(w["kitchen"].provider_id), "meal_slots": "lunch,dinner"})
    assert bad.status_code == 400 and bad.json()["code"] == "MEAL_NOT_SERVED"


# ── Points 5 + 6: PIN check and editing the address at checkout ─

def test_kitchen_must_serve_the_delivery_pin(client, db):
    w = f.world(db)
    f.pincode(db, pin=560099)
    _, far, far_hdr = f.customer(db, balance="1000", pin=560099)
    r = _extra(client, w, user_auth=far_hdr, address=far)
    assert r.status_code == 400 and r.json()["code"] == "ADDRESS_NOT_SERVICEABLE"
    assert r.json()["message"] == PIN_MESSAGE
    q = client.post(f"{S}/quote", headers=far_hdr, json={
        "vendor_id": str(w["kitchen"].provider_id), "package_id": str(w["package"].package_id),
        "plan_id": str(w["plan"].subscription_plan_id), "address_id": str(far.user_address_id),
        "start_date": "2026-10-05", "quantity": 1,
    })
    assert q.status_code == 400 and q.json()["message"] == PIN_MESSAGE

    listed = client.get(f"{M}/packages", headers=w["user_auth"], params={"pin_code": f.PIN}).json()["packages"][0]
    assert listed["service_pincodes"] == [str(f.PIN)]
    _, admin_hdr = f.admin(db, role="super_admin")
    assert client.post(f"{A}/providers/{w['kitchen'].provider_id}/service-areas", headers=admin_hdr,
                       json={"pincode": 560099}).status_code == 200
    assert _extra(client, w, user_auth=far_hdr, address=far).status_code == 200


def test_changed_address_pin_is_checked_again_before_ordering(client, db):
    w = f.world(db)
    f.pincode(db, pin=560099)
    addr = str(w["address"].user_address_id)
    body = {"vendor_id": str(w["kitchen"].provider_id), "address_id": addr, "delivery_date": "2026-10-05",
            "meal_slot": "lunch", "items": [{"package_id": str(w["package"].package_id), "quantity": 1}]}
    assert client.post(f"{O}/extra/quote", headers=w["user_auth"], json=body).status_code == 200

    assert client.put(f"/api/v1/user/address/{addr}", headers=w["user_auth"], json={"pin_code": "560099"}).status_code == 200
    moved = client.post(f"{O}/extra/quote", headers=w["user_auth"], json=body)
    assert moved.status_code == 400 and moved.json()["message"] == PIN_MESSAGE
    assert client.post(f"{O}/extra", headers=w["user_auth"], json=body).status_code == 400

    assert client.put(f"/api/v1/user/address/{addr}", headers=w["user_auth"], json={"pin_code": str(f.PIN)}).status_code == 200
    placed = client.post(f"{O}/extra", headers=w["user_auth"], json=body)
    assert placed.status_code == 200, placed.text
    order = db.query(ExtraOrder).one()
    assert str(order.address_reference_id) == addr
    # the address the order was validated with cannot move to another pincode any more
    assert client.put(f"/api/v1/user/address/{addr}", headers=w["user_auth"], json={"pin_code": "560099"}).status_code == 400


# ── Points 7 + 8: kitchens per delivery partner ───────────────

def test_partner_serves_several_kitchens_and_sees_them(client, db):
    w = f.world(db)
    k2, _ = f.provider(db)
    boy, boy_hdr = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")

    assert _give_kitchen(client, admin_hdr, boy, w["kitchen"]).json()["assigned_vendor_count"] == 1
    second = _give_kitchen(client, admin_hdr, boy, k2)
    assert second.status_code == 200 and second.json()["assigned_vendor_count"] == 2
    again = _give_kitchen(client, admin_hdr, boy, w["kitchen"]).json()
    assert again["action"] == "unchanged"
    assert db.query(DeliveryPartnerVendor).filter(DeliveryPartnerVendor.status == "active").count() == 2

    detail = client.get(f"{A}/delivery-boys/{boy.delivery_boy_id}", headers=admin_hdr).json()
    assert detail["assigned_vendor_count"] == 2
    names = {v["business_name"] for v in detail["assigned_vendors"]}
    assert names == {w["kitchen"].business_name, k2.business_name}
    assert all(v["address"] and v["mobile_number"] for v in detail["assigned_vendors"])
    row = next(b for b in client.get(f"{A}/delivery-boys", headers=admin_hdr).json()["delivery_boys"]
               if b["delivery_boy_id"] == str(boy.delivery_boy_id))
    assert row["assigned_vendor_count"] == 2

    mine = client.get(f"{D}/vendors", headers=boy_hdr).json()
    assert mine["total"] == 2 and {v["business_name"] for v in mine["vendors"]} == names
    assert client.get(f"{D}/profile", headers=boy_hdr).json()["profile"]["assigned_vendor_count"] == 2
    assert client.get(f"{D}/vendors/{k2.provider_id}", headers=boy_hdr).status_code == 200
    assert db.query(DeliveryBoyNotification).filter(DeliveryBoyNotification.type == "vendor_assigned").count() == 2

    # removing one kitchen leaves the other alone
    gone = client.request("DELETE", f"{A}/delivery-boys/{boy.delivery_boy_id}/vendors/{w['kitchen'].provider_id}",
                          headers=admin_hdr, json={"reason": "route change"})
    assert gone.status_code == 200 and gone.json()["assigned_vendor_count"] == 1
    assert [v["provider_id"] for v in client.get(f"{D}/vendors", headers=boy_hdr).json()["vendors"]] == [str(k2.provider_id)]
    assert client.get(f"{D}/vendors/{w['kitchen'].provider_id}", headers=boy_hdr).status_code == 404

    # only admins manage this; other partners never see these kitchens
    other, other_hdr = f.delivery_boy(db)
    assert client.get(f"{D}/vendors/{k2.provider_id}", headers=other_hdr).status_code == 404
    assert _give_kitchen(client, w["kitchen_auth"], other, k2).status_code in (401, 403)
    assert _give_kitchen(client, boy_hdr, other, k2).status_code in (401, 403)


def test_moving_a_kitchen_moves_work_not_yet_picked_up(client, db):
    w = f.world(db, balance="5000")
    a, a_hdr = f.delivery_boy(db)
    b, _ = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")
    _give_kitchen(client, admin_hdr, a, w["kitchen"])
    sub_id = _subscribe(client, w)
    meals = _meals(db, sub_id)
    assert all(m.delivery_boy_reference_id == a.delivery_boy_id for m in meals)

    today = meals[0]
    r = client.put(f"{K}/subscription-orders/{today.order_id}/status", headers=w["kitchen_auth"], json={"status": "preparing"})
    assert r.status_code == 200
    assert client.put(f"{D}/orders/{today.order_id}/pickup", headers=a_hdr,
                      json={"pickup_code": f.pickup_code(db, w["kitchen"])}).status_code == 200

    moved = _give_kitchen(client, admin_hdr, b, w["kitchen"]).json()
    assert moved["action"] == "moved" and moved["previous_delivery_boy_id"] == str(a.delivery_boy_id)
    assert moved["kept_with_previous_partner"] == 1
    meals = _meals(db, sub_id)
    assert meals[0].delivery_boy_reference_id == a.delivery_boy_id  # in A's hands
    assert all(m.delivery_boy_reference_id == b.delivery_boy_id for m in meals[1:])
    assert db.query(Subscription).filter(Subscription.subscription_id == sub_id).one().delivery_boy_reference_id == b.delivery_boy_id
    rows = db.query(DeliveryPartnerVendor).order_by(DeliveryPartnerVendor.assigned_at).all()
    assert [(r.status, r.end_reason) for r in rows] == [("ended", "moved_to_other_partner"), ("active", None)]
    assert client.get(f"{D}/vendors", headers=a_hdr).json()["total"] == 0


# ── Point 9: new work goes to the kitchen's partner ───────────

def test_new_orders_and_subscriptions_go_to_the_kitchens_partner(client, db):
    w = f.world(db, balance="5000")
    boy, boy_hdr = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")
    _give_kitchen(client, admin_hdr, boy, w["kitchen"])

    sub_id = _subscribe(client, w)
    sub = db.query(Subscription).filter(Subscription.subscription_id == sub_id).one()
    assert sub.delivery_boy_reference_id == boy.delivery_boy_id
    assert all(m.delivery_boy_reference_id == boy.delivery_boy_id for m in _meals(db, sub_id))

    placed = _extra(client, w, day="2026-10-06")
    assert placed.status_code == 200 and placed.json()["delivery_partner_assigned"] is True
    db.expire_all()
    assert db.query(ExtraOrder).one().delivery_boy_reference_id == boy.delivery_boy_id

    dash = client.get(f"{D}/dashboard", headers=boy_hdr).json()
    assert dash["assigned_vendor_count"] == 1 and dash["counts"]["total"] == 1
    kitchen_partner = client.get(f"{P}/delivery-partner", headers=w["kitchen_auth"]).json()["delivery_partner"]
    assert kitchen_partner["delivery_boy_id"] == str(boy.delivery_boy_id)

    # the nightly generation and its retries add nothing twice
    before = len(_meals(db, sub_id))
    jobs._generate(db)
    jobs._generate(db)
    db.commit()
    assert len(_meals(db, sub_id)) == before
    from app.models.subscription_delivery_assignment_model import SubscriptionDeliveryAssignment
    assert db.query(SubscriptionDeliveryAssignment).filter(SubscriptionDeliveryAssignment.status == "active").count() == 1


def test_without_a_partner_work_waits_flagged_until_one_is_assigned(client, db):
    w = f.world(db, balance="5000")
    sub_id = _subscribe(client, w)
    assert _extra(client, w, day="2026-10-06").json()["delivery_partner_assigned"] is False
    assert all(m.delivery_boy_reference_id is None for m in _meals(db, sub_id))

    _, admin_hdr = f.admin(db, role="moderator")
    flags = client.get(f"{A}/dashboard", headers=admin_hdr, params={"refresh": "true"}).json()["needs_delivery_partner"]
    assert flags["kitchens_without_partner"] == 1 and flags["subscriptions"] == 1 and flags["one_time_orders"] == 1
    kitchen = client.get(f"{A}/providers/{w['kitchen'].provider_id}", headers=admin_hdr).json()
    assert kitchen["delivery_partner"] is None and kitchen["needs_partner"] == {"subscriptions": 1, "one_time_orders": 1}

    boy, _ = f.delivery_boy(db)
    given = _give_kitchen(client, admin_hdr, boy, w["kitchen"]).json()
    assert given["subscriptions_assigned"] == 1 and given["one_time_orders_assigned"] == 1
    assert all(m.delivery_boy_reference_id == boy.delivery_boy_id for m in _meals(db, sub_id))
    db.expire_all()
    assert db.query(ExtraOrder).one().delivery_boy_reference_id == boy.delivery_boy_id


def test_one_partner_two_kitchens_each_task_keeps_its_kitchen(client, db):
    w = f.world(db, balance="5000")
    k2, k2_hdr = f.provider(db)
    pkg2 = f.package(db, k2, w["category"])
    boy, _ = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")
    _give_kitchen(client, admin_hdr, boy, w["kitchen"])
    _give_kitchen(client, admin_hdr, boy, k2)

    s1 = _subscribe(client, w)
    s2 = _subscribe(client, w, kitchen=k2, package=pkg2)
    for sub_id, kitchen in ((s1, w["kitchen"]), (s2, k2)):
        meals = _meals(db, sub_id)
        assert all(m.vendor_reference_id == kitchen.provider_id and m.delivery_boy_reference_id == boy.delivery_boy_id
                   for m in meals)

    client.request("DELETE", f"{A}/delivery-boys/{boy.delivery_boy_id}/vendors/{w['kitchen'].provider_id}", headers=admin_hdr)
    assert all(m.delivery_boy_reference_id is None for m in _meals(db, s1))
    assert all(m.delivery_boy_reference_id == boy.delivery_boy_id for m in _meals(db, s2))


# ── Point 10: partner payout ──────────────────────────────────

def test_partner_is_paid_the_configured_payout_once_per_completed_delivery(client, db):
    w = f.world(db, balance="5000")
    boy, boy_hdr = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="super_admin")
    _give_kitchen(client, admin_hdr, boy, w["kitchen"])
    sub_id = _subscribe(client, w)
    meals = _meals(db, sub_id)

    assert _deliver_meal(client, db, w["kitchen_auth"], w["kitchen"], meals[0], boy_hdr).status_code == 200
    retry = client.put(f"{D}/orders/{meals[0].order_id}/deliver", headers=boy_hdr, json={"otp": f.delivery_code(meals[0])})
    assert retry.status_code == 200 and retry.json()["already_done"] is True
    assert _wallet(db, boy) == Decimal("30.00")

    txn = db.query(DeliveryBoyWalletTransaction).one()
    assert (txn.type, txn.reason, txn.reference_type, txn.reference_id, txn.delivery_boy_reference_id) == (
        "credit", "delivery_payout", "order", meals[0].order_id, boy.delivery_boy_id)
    assert txn.amount == Decimal("30.00") and txn.created_at is not None and "payout setting v1" in txn.description

    # the admin changes the payout: the next delivery of the SAME running subscription uses it
    r = client.put(f"{A}/pricing/delivery_partner_payout", headers=admin_hdr, json={
        "calc_type": "fixed", "value": "45", "applies_to": "all", "charge_basis": "per_delivery",
        "is_active": True, "change_reason": "fuel price revision",
    })
    assert r.status_code == 200, r.text
    clock.freeze(datetime(2026, 10, 6, 5, 0))
    assert _deliver_meal(client, db, w["kitchen_auth"], w["kitchen"], meals[1], boy_hdr).status_code == 200
    assert _wallet(db, boy) == Decimal("75.00")

    review = payout_audit.review(db)
    assert review["duplicate_payouts"]["count"] == 0 and review["delivered_without_payout"]["count"] == 0
    assert review["paid_but_not_delivered"]["count"] == 0 and review["payouts"]["total"] == "75.00"


def test_failed_and_cancelled_deliveries_pay_the_partner_nothing(client, db):
    w = f.world(db, balance="5000")
    boy, boy_hdr = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="super_admin")
    _give_kitchen(client, admin_hdr, boy, w["kitchen"])
    sub_id = _subscribe(client, w)
    meal = _meals(db, sub_id)[0]
    oid = str(meal.order_id)
    client.put(f"{K}/subscription-orders/{oid}/status", headers=w["kitchen_auth"], json={"status": "preparing"})
    client.put(f"{D}/orders/{oid}/pickup", headers=boy_hdr, json={"pickup_code": f.pickup_code(db, w["kitchen"])})
    client.put(f"{D}/orders/{oid}/arrived", headers=boy_hdr)
    clock.freeze(datetime(2026, 10, 5, 5, 11))
    r = client.put(f"{D}/orders/{oid}/failed", headers=boy_hdr, json={"reason": "customer_unavailable"})
    assert r.status_code == 200, r.text
    assert _wallet(db, boy) == Decimal("0.00")  # kitchen paid (food cooked), partner not

    # the admin confirms the customer did get it: now the delivery counts, paid once
    r = client.put(f"{A}/orders/subscription-orders/{oid}/status", headers=admin_hdr,
                   json={"status": "delivered", "reason": "customer confirmed by phone"})
    assert r.status_code == 200, r.text
    assert _wallet(db, boy) == Decimal("30.00")

    # a cancelled one-time order is never paid
    placed = _extra(client, w, day="2026-10-06").json()
    extra_id = placed["orders"][0]["extra_order_id"]
    r = client.put(f"{A}/orders/extra-orders/{extra_id}/status", headers=admin_hdr,
                   json={"status": "cancelled", "reason": "kitchen closed early"})
    assert r.status_code == 200, r.text
    assert _wallet(db, boy) == Decimal("30.00")


def test_one_time_checkout_is_one_paid_trip(client, db):
    w = f.world(db, balance="5000")
    second = f.package(db, w["kitchen"], w["category"])
    boy, boy_hdr = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")
    _give_kitchen(client, admin_hdr, boy, w["kitchen"])
    placed = _extra(client, w, items=[{"package_id": str(w["package"].package_id), "quantity": 1},
                                      {"package_id": str(second.package_id), "quantity": 2}])
    assert placed.status_code == 200, placed.text
    first_id = placed.json()["orders"][0]["extra_order_id"]
    for line in placed.json()["orders"]:
        for status in ("confirmed", "preparing"):
            assert client.put(f"{K}/extra/{line['extra_order_id']}/status", headers=w["kitchen_auth"],
                              json={"status": status}).status_code == 200
    assert client.put(f"{D}/extra-orders/{first_id}/pickup", headers=boy_hdr,
                      json={"pickup_code": f.pickup_code(db, w["kitchen"])}).status_code == 200
    line = db.query(ExtraOrder).filter(ExtraOrder.extra_order_id == first_id).one()
    r = client.put(f"{D}/extra-orders/{first_id}/deliver", headers=boy_hdr, json={"otp": f.delivery_code(line)})
    assert r.status_code == 200, r.text
    assert _wallet(db, boy) == Decimal("30.00")
    assert db.query(DeliveryBoyWalletTransaction).count() == 1


def test_payout_switched_off_credits_nothing(client, db):
    w = f.world(db, balance="5000")
    boy, boy_hdr = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="super_admin")
    _give_kitchen(client, admin_hdr, boy, w["kitchen"])
    client.put(f"{A}/pricing/delivery_partner_payout", headers=admin_hdr, json={
        "calc_type": "fixed", "value": "30", "charge_basis": "per_delivery", "is_active": False,
        "change_reason": "payouts handled offline",
    })
    sub_id = _subscribe(client, w)
    assert _deliver_meal(client, db, w["kitchen_auth"], w["kitchen"], _meals(db, sub_id)[0], boy_hdr).status_code == 200
    assert _wallet(db, boy) == Decimal("0.00")


# ── Point 11: package ratings ─────────────────────────────────

def _delivered_order(db, user, address, kitchen, pkg):
    order = ExtraOrder(
        extra_order_id=uuid.uuid4(), user_reference_id=user.user_id, vendor_reference_id=kitchen.provider_id,
        address_reference_id=address.user_address_id, package_reference_id=pkg.package_id, quantity=1,
        unit_price=Decimal("180"), total_price=Decimal("180"), delivery_date=today_local(), meal_slot="lunch",
        status="delivered",
    )
    db.add(order)
    db.commit()
    return order


def test_every_package_keeps_its_own_rating_for_everyone(client, db):
    w = f.world(db)
    standard, premium = w["package"], f.package(db, w["kitchen"], w["category"], price="250")
    raters = []
    for stars in (5, 4, 3):
        user, address, hdr = f.customer(db)
        order = _delivered_order(db, user, address, w["kitchen"], standard)
        r = client.post(R, headers=hdr, json={"order_id": str(order.extra_order_id), "vendor_rating": 5,
                                              "package_rating": stars, "review_text": "Nice"})
        assert r.status_code == 200 and r.json()["updated"] is False, r.text
        raters.append((hdr, order))

    _, _, stranger = f.customer(db)
    listing = {p["package_id"]: p for p in client.get(f"{M}/packages", headers=stranger, params={"pin_code": f.PIN}).json()["packages"]}
    assert (listing[str(standard.package_id)]["rating_average"], listing[str(standard.package_id)]["rating_count"]) == (4.0, 3)
    assert listing[str(standard.package_id)]["rating_label"] == "4.0 (3 reviews)"
    assert listing[str(premium.package_id)]["rating_count"] == 0
    assert listing[str(premium.package_id)]["rating_label"] == "No ratings yet"
    detail = client.get(f"{M}/packages/{standard.package_id}", headers=stranger).json()
    assert detail["rating_average"] == 4.0 and detail["review_total"] == 3 and len(detail["reviews"]) == 3

    # rating the same order again edits the review instead of adding one
    hdr, order = raters[0]
    again = client.post(R, headers=hdr, json={"order_id": str(order.extra_order_id), "vendor_rating": 4, "package_rating": 2})
    assert again.status_code == 200 and again.json()["updated"] is True
    pkg = client.get(f"{R}/package/{standard.package_id}", headers=stranger,
                     params={"provider_id": str(w["kitchen"].provider_id)}).json()
    assert (pkg["rating_average"], pkg["rating_count"]) == (3.0, 3)

    # the kitchen and admin see the same package rating
    mine = {p["package_id"]: p for p in client.get(f"/api/v1/menu/list/{w['kitchen'].provider_id}", headers=w["kitchen_auth"]).json()}
    assert mine[str(standard.package_id)]["rating_count"] == 3
    _, admin_hdr = f.admin(db, role="moderator")
    admin_row = next(p for p in client.get(f"{A}/packages", headers=admin_hdr).json()["packages"]
                     if p["package_id"] == str(standard.package_id))
    assert admin_row["rating_average"] == 3.0


def test_invalid_or_unearned_ratings_are_refused(client, db):
    w = f.world(db)
    other_pkg = f.package(db, w["kitchen"], w["category"])
    order = _delivered_order(db, w["user"], w["address"], w["kitchen"], w["package"])
    oid = str(order.extra_order_id)
    assert client.post(R, headers=w["user_auth"], json={"order_id": oid, "vendor_rating": 5, "package_rating": 6}).status_code == 422
    assert client.post(R, headers=w["user_auth"], json={"order_id": oid, "vendor_rating": 0}).status_code == 422
    mismatch = client.post(R, headers=w["user_auth"], json={"order_id": oid, "vendor_rating": 5,
                                                             "package_id": str(other_pkg.package_id)})
    assert mismatch.status_code == 400
    _, _, someone_else = f.customer(db)
    assert client.post(R, headers=someone_else, json={"order_id": oid, "vendor_rating": 5}).status_code == 400
    order.status = "out_for_delivery"
    db.commit()
    assert client.post(R, headers=w["user_auth"], json={"order_id": oid, "vendor_rating": 5}).status_code == 400


# ── Point 12: skipped meals reach the kitchen ─────────────────

def test_skip_tells_the_right_kitchen_once_with_meal_and_date(client, db):
    w = f.world(db, balance="5000")
    boy, boy_hdr = f.delivery_boy(db)
    _, admin_hdr = f.admin(db, role="moderator")
    _give_kitchen(client, admin_hdr, boy, w["kitchen"])
    sub_id = _subscribe(client, w)
    other_kitchen, _ = f.provider(db)
    other_pkg = f.package(db, other_kitchen, w["category"])
    _, other_addr, other_hdr = f.customer(db, balance="5000")
    _subscribe(client, w, kitchen=other_kitchen, package=other_pkg, user_auth=other_hdr, address=other_addr)

    meals = _meals(db, sub_id)
    future = next(m for m in meals if str(m.order_date) == "2026-10-07")
    r = client.put(f"{S}/{sub_id}/orders/{future.order_id}/skip", headers=w["user_auth"])
    assert r.status_code == 200 and r.json()["already_skipped"] is False, r.text

    notes = db.query(ProviderNotification).filter(ProviderNotification.type == "meal_skipped").all()
    assert len(notes) == 1 and notes[0].provider_reference_id == w["kitchen"].provider_id
    note = notes[0]
    assert note.title == "Meal Skipped by Customer"
    assert note.body == ("A customer has skipped their lunch meal scheduled for 7 October 2026. "
                         "Please exclude this meal from preparation and delivery for that date.")
    assert note.data["meal_date"] == "2026-10-07" and note.data["meal_slot"] == "lunch"
    assert note.data["package_names"] == [w["package"].package_name]
    assert note.data["subscription_id"] == sub_id and note.data["customer_ref"]
    assert "phone" not in json.dumps(note.data)

    # retrying the same skip changes nothing and notifies nobody again
    again = client.put(f"{S}/{sub_id}/orders/{future.order_id}/skip", headers=w["user_auth"])
    assert again.status_code == 200 and again.json()["already_skipped"] is True
    assert db.query(ProviderNotification).filter(ProviderNotification.type == "meal_skipped").count() == 1

    # today's meal: a second notice, for today's date; it leaves the partner's list
    r = client.put(f"{S}/{sub_id}/orders/{meals[0].order_id}/skip", headers=w["user_auth"])
    assert r.status_code == 200, r.text
    db.expire_all()
    todays = db.query(ProviderNotification).filter(ProviderNotification.type == "meal_skipped").order_by(
        ProviderNotification.created_at.desc()).first()
    assert todays.data["meal_date"] == "2026-10-05" and "5 October 2026" in todays.body
    kitchen_notes = client.get(f"{P}/notifications", headers=w["kitchen_auth"]).json()
    skipped = [n for n in kitchen_notes["notifications"] if n["type"] == "meal_skipped"]
    assert len(skipped) == 2 and kitchen_notes["unread"] >= 2
    dash = client.get(f"{D}/dashboard", headers=boy_hdr).json()
    assert all(c["status"] != "skipped" for c in dash["today_orders"])


def test_skip_is_kept_when_the_push_cannot_be_sent(client, db, monkeypatch):
    def broken(request):
        return httpx.Response(503, json={"error": "unavailable"})

    monkeypatch.setattr(push, "PUSH_PROVIDER", "expo")
    monkeypatch.setattr(push, "_transport", httpx.MockTransport(broken))
    monkeypatch.setattr(push, "_sync", True)
    w = f.world(db, balance="5000")
    client.post("/api/v1/provider/push-token", headers=w["kitchen_auth"], json={"token": "ExponentPushToken[abcdefghijklmnop]"})
    sub_id = _subscribe(client, w)
    meal = _meals(db, sub_id)[2]
    r = client.put(f"{S}/{sub_id}/orders/{meal.order_id}/skip", headers=w["user_auth"])
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Order).filter(Order.order_id == meal.order_id).one().status == "skipped"
    assert db.query(ProviderNotification).filter(ProviderNotification.type == "meal_skipped").count() == 1
