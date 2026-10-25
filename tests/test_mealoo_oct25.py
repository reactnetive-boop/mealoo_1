"""
Units, vendor Home batches, delivery code, skips / switches on the delivery
side, price breakup, vendor holidays (casual + emergency) - every scenario of
mealoo_claude_prompt.md section 10 that the backend owns, numbered as there.

Clock: Monday 5 Oct 2026, 05:00 IST (tests/conftest.py) unless a test moves it.
"""

import threading
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core import clock
from app.core.database import SessionLocal
from app.domain import emergency_holiday, holidays, notify, price_breakup
from app.models.delivery_boy_notification_model import DeliveryBoyNotification
from app.models.extra_order_model import ExtraOrder
from app.models.menu_package_item_model import MenuPackageItem
from app.models.notification_model import Notification
from app.models.order_model import Order
from app.models.skip_credit_model import SkipCreditTransaction
from app.models.subscription_model import Subscription
from app.models.vendor_holiday_model import VendorHoliday, VendorHolidayMeal
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from app.schedulers import jobs
from tests import factories as f

API = "/api/v1"
S = f"{API}/user/subscription"
K = f"{API}/provider/orders"
D = f"{API}/delivery"
H = f"{API}/provider/holidays"
TODAY = date(2026, 10, 5)


def _ok(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url}: {r.status_code} {r.text}"
    return r.json()


def _subscribe(client, w, *, start="2026-10-05", plan=None, package=None, kitchen=None, user_auth=None,
               address=None, qty=1, **extra):
    body = {
        "vendor_id": str((kitchen or w["kitchen"]).provider_id),
        "plan_id": str((plan or w["plan"]).subscription_plan_id),
        "address_id": str((address or w["address"]).user_address_id),
        "start_date": start,
        "items": [{"package_id": str((package or w["package"]).package_id), "quantity": qty}],
        **extra,
    }
    return client.post(S, headers=user_auth or w["user_auth"], json=body)


def _sub_id(client, w, **kw) -> str:
    return _ok(_subscribe(client, w, **kw))["subscription_id"]


def _quote(client, w, *, start="2026-10-05", plan=None, package=None, kitchen=None, qty=1):
    return _ok(client.post(f"{S}/quote", headers=w["user_auth"], json={
        "vendor_id": str((kitchen or w["kitchen"]).provider_id),
        "package_id": str((package or w["package"]).package_id),
        "plan_id": str((plan or w["plan"]).subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": start, "quantity": qty,
    }))


def _meals(db, sub_id):
    db.expire_all()
    return (db.query(Order).filter(Order.subscription_reference_id == sub_id)
            .order_by(Order.order_date, Order.meal_slot).all())


def _meal(db, sub_id, day, slot="lunch"):
    db.expire_all()
    return db.query(Order).filter(Order.subscription_reference_id == sub_id, Order.order_date == day,
                                  Order.meal_slot == slot).one()


def _balance(db, user) -> Decimal:
    db.expire_all()
    return db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance


def _sum(breakup) -> Decimal:
    return sum((Decimal(l["amount"]) for l in breakup["lines"] if l["in_total"]), Decimal("0"))


def _tags(view) -> set:
    return {t["type"] for t in view.get("change_tags", [])}


def _price(client, admin_hdr, key, **body):
    payload = {"calc_type": "fixed", "charge_basis": "per_order", "applies_to": "all", "is_active": True,
               "change_reason": "test setup", **body}
    _ok(client.put(f"{API}/admin/pricing/{key}", headers=admin_hdr, json=payload))


def _gst(db, active=True):
    from app.models.pricing_component_model import PricingComponent
    db.add(PricingComponent(component_key="gst", label="GST", calc_type="percentage", value=Decimal("5"),
                            applies_to="all", charge_basis="per_order", is_customer_facing=True, is_active=active,
                            version=1))
    db.commit()


# ══ Section 1: units ═════════════════════════════════════════

def test_01_menu_item_without_unit_is_created(client, db):
    w = f.world(db)
    pkg = _ok(client.post(f"{API}/menu/package", headers=w["kitchen_auth"], json={
        "category_id": str(w["category"].category_id), "package_name": "Veg Thali", "meal_type": ["lunch"],
        "food_type": "veg", "price": "150", "is_subscription_available": True, "subscription_price": "150",
        "items": [{"item_name": "Roti"}, {"item_name": "Dal"}],
    }))
    r = _ok(client.post(f"{API}/package/item/add", headers=w["kitchen_auth"],
                        json={"package_id": pkg["package_id"], "item_name": "Rice"}))
    assert r["success"] is True
    items = db.query(MenuPackageItem).filter(MenuPackageItem.package_reference_id == pkg["package_id"]).all()
    assert {i.item_name for i in items} == {"Roti", "Dal", "Rice"}
    assert all(i.quantity_unit is None for i in items)


def test_02_item_with_a_stored_unit_still_loads_edits_and_saves(client, db):
    w = f.world(db)
    item = MenuPackageItem(package_reference_id=w["package"].package_id, item_name="Paneer", quantity="400 g",
                           quantity_value=Decimal("400"), quantity_unit="g", item_order=2)
    db.add(item)
    db.commit()
    detail = _ok(client.get(f"{API}/menu/get/{w['package'].package_id}", headers=w["kitchen_auth"]))
    assert any(i["item_name"] == "Paneer" for i in detail.get("items", detail.get("package", {}).get("items", [])))
    r = _ok(client.put(f"{API}/package/item/update/{item.item_id}", headers=w["kitchen_auth"],
                       json={"item_name": "Paneer tikka"}))
    assert r["success"] is True
    db.expire_all()
    stored = db.query(MenuPackageItem).filter(MenuPackageItem.item_id == item.item_id).one()
    assert stored.quantity_unit == "g"  # existing data is never dropped


def test_03_no_unit_or_null_text_where_units_used_to_be(client, db):
    w = f.world(db)
    db.add(MenuPackageItem(package_reference_id=w["package"].package_id, item_name="Curd", quantity="250 ml",
                           quantity_value=Decimal("250"), quantity_unit="ml", item_order=3))
    db.commit()
    detail = _ok(client.get(f"{API}/user/menu/packages/{w['package'].package_id}", headers=w["user_auth"]))
    for item in detail["items"]:
        assert set(item) == {"item_id", "item_name", "item_order"}
    _sub_id(client, w)
    summary = _ok(client.get(f"{K}/food-summary", headers=w["kitchen_auth"]))
    assert summary["items"] and all(set(i) == {"item_name", "total_servings"} for i in summary["items"])
    shown = [i["item_name"] for i in detail["items"]] + [i["item_name"] for i in summary["items"]]
    for label in shown:
        for bad in ("None", "undefined", "null", "()", " g", " ml"):
            assert bad not in label


# ══ Sections 2-3: vendor Home batch and bulk Ready for Pickup ═

def _three_customers(client, db, w):
    subs = [_sub_id(client, w)]
    for _ in range(2):
        user, address, auth = f.customer(db, balance="5000")
        subs.append(_sub_id(client, w, user_auth=auth, address=address))
    return subs


def test_04_home_shows_next_batch_without_skipped_or_cancelled_meals(client, db):
    w = f.world(db)
    subs = _three_customers(client, db, w)
    skip = _meal(db, subs[0], TODAY)
    _ok(client.put(f"{S}/{subs[0]}/orders/{skip.order_id}/skip", headers=w["user_auth"]))
    batch = _ok(client.get(f"{K}/next-batch", headers=w["kitchen_auth"]))["batch"]
    assert batch["date"] == "2026-10-05" and batch["meal_slot"] == "lunch"
    assert batch["counts"]["total"] == 2 and batch["excluded"]["skipped"] == 1
    assert batch["item_summary"] == [{"package_name": w["package"].package_name, "quantity": 2}]
    assert batch["delivery_window"] == {"from": "12:00", "to": "14:30"}


def test_05_start_preparing_then_ready_from_home_in_place(client, db):
    w = f.world(db)
    _three_customers(client, db, w)
    body = {"order_date": "2026-10-05", "meal_slot": "lunch"}
    r = _ok(client.put(f"{K}/batch/status", headers=w["kitchen_auth"], json={**body, "status": "preparing"}))
    assert r["changed"] == 3 and r["batch"]["status"] == "preparing" and r["batch"]["counts"]["preparing"] == 3
    again = _ok(client.put(f"{K}/batch/status", headers=w["kitchen_auth"], json={**body, "status": "preparing"}))
    assert again["changed"] == 0 and again["already_done"] is True
    r = _ok(client.put(f"{K}/batch/status", headers=w["kitchen_auth"], json={**body, "status": "ready_for_pickup"}))
    assert r["changed"] == 3
    db.expire_all()
    assert {o.status for o in db.query(Order).filter(Order.order_date == TODAY)} == {"ready_for_pickup"}


def test_06_next_batch_appears_after_the_current_one_is_ready(client, db):
    w = f.world(db)
    _three_customers(client, db, w)
    r = _ok(client.put(f"{K}/batch/status", headers=w["kitchen_auth"],
                       json={"order_date": "2026-10-05", "meal_slot": "lunch", "status": "ready_for_pickup"}))
    assert r["batch"]["date"] == "2026-10-06" and r["batch"]["meal_slot"] == "lunch"
    assert r["batch"]["can_mark_ready"] is False  # not its delivery day yet


def test_07_bulk_ready_moves_only_eligible_orders_and_dialog_count_matches(client, db):
    w = f.world(db)
    subs = _three_customers(client, db, w)
    _ok(client.put(f"{S}/{subs[0]}/orders/{_meal(db, subs[0], TODAY).order_id}/skip", headers=w["user_auth"]))
    # an unconfirmed one-time order is not eligible either
    _ok(client.post(f"{API}/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-05", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    }))
    preview = _ok(client.get(f"{K}/ready-today", headers=w["kitchen_auth"]))
    assert preview["eligible"] == 2 and preview["awaiting_confirmation"] == 1
    r = _ok(client.post(f"{K}/ready-today", headers=w["kitchen_auth"], json={"expected_count": 2}))
    assert r["changed"] == preview["eligible"]
    db.expire_all()
    assert db.query(Order).filter(Order.status == "ready_for_pickup").count() == 2
    assert db.query(Order).filter(Order.status == "skipped").count() == 1
    assert db.query(ExtraOrder).one().status == "pending"


def test_08_bulk_ready_twice_changes_nothing_and_notifies_once(client, db):
    w = f.world(db)
    f.delivery_boy(db, kitchen=w["kitchen"])
    _three_customers(client, db, w)
    first = _ok(client.post(f"{K}/ready-today", headers=w["kitchen_auth"]))
    notes = db.query(DeliveryBoyNotification).filter(DeliveryBoyNotification.type == "order_ready").count()
    second = _ok(client.post(f"{K}/ready-today", headers=w["kitchen_auth"]))
    assert first["changed"] == 3 and first["partners_notified"] == 1
    assert second["changed"] == 0 and second["already_done"] is True
    db.expire_all()
    assert db.query(DeliveryBoyNotification).filter(DeliveryBoyNotification.type == "order_ready").count() == notes == 1


# ══ Section 4: delivery code (server side) ═══════════════════

def _picked_up(client, db, w):
    boy, boy_auth = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _sub_id(client, w)
    meal = _meal(db, sub_id, TODAY)
    _ok(client.post(f"{K}/ready-today", headers=w["kitchen_auth"]))
    _ok(client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth,
                   json={"pickup_code": f.pickup_code(db, w["kitchen"])}))
    db.expire_all()
    return boy_auth, db.query(Order).filter(Order.order_id == meal.order_id).one()


def test_09_correct_code_delivers(client, db):
    w = f.world(db)
    boy_auth, meal = _picked_up(client, db, w)
    r = _ok(client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": f.delivery_code(meal)}))
    assert r["status"] == "delivered" and r["already_done"] is False


def test_10_wrong_code_is_refused_and_can_be_retried(client, db):
    w = f.world(db)
    boy_auth, meal = _picked_up(client, db, w)
    r = client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": f.wrong_code(f.delivery_code(meal))})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_DELIVERY_CODE"
    db.expire_all()
    assert db.query(Order).filter(Order.order_id == meal.order_id).one().status == "picked_up"
    _ok(client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": f.delivery_code(meal)}))


def test_12_already_delivered_order_answers_success_without_changes(client, db):
    w = f.world(db)
    boy_auth, meal = _picked_up(client, db, w)
    code = f.delivery_code(meal)
    _ok(client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": code}))
    again = _ok(client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": code}))
    assert again["already_done"] is True and again["message"] == "Order already delivered"


# ══ Section 5: skips and switches on the delivery side ═══════

def test_14_skipped_lunch_shows_skipped_and_leaves_route_and_prep(client, db):
    w = f.world(db)
    boy, boy_auth = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _sub_id(client, w)
    meal = _meal(db, sub_id, TODAY)
    _ok(client.put(f"{S}/{sub_id}/orders/{meal.order_id}/skip", headers=w["user_auth"]))
    rows = _ok(client.get(f"{D}/orders", headers=boy_auth))["orders"]
    row = next(o for o in rows if o["order_id"] == str(meal.order_id))
    assert row["status"] == "skipped" and row["on_route"] is False and "SKIPPED" in _tags(row)
    board = _ok(client.get(f"{D}/dashboard", headers=boy_auth))
    assert all(c["order_id"] != str(meal.order_id) for c in board["today_orders"])
    assert board["next_delivery"] is None or board["next_delivery"]["order_id"] != str(meal.order_id)
    kitchen_rows = _ok(client.get(f"{K}/subscription-orders", headers=w["kitchen_auth"]))["orders"]
    krow = next(o for o in kitchen_rows if o["order_id"] == str(meal.order_id))
    assert krow["on_prep_list"] is False and "SKIPPED" in _tags(krow)
    assert _ok(client.get(f"{K}/food-summary", headers=w["kitchen_auth"]))["total_orders_count"] == 0


def test_15_skipping_breakfast_keeps_lunch_active(client, db):
    w = f.world(db, meal_type="breakfast,lunch", plan_slot="breakfast_lunch")
    clock.freeze(datetime(2026, 10, 4, 20, 0))  # the evening before, so breakfast can start tomorrow
    sub_id = _sub_id(client, w, start="2026-10-05")
    clock.freeze(datetime(2026, 10, 5, 5, 0))
    breakfast = _meal(db, sub_id, TODAY, "breakfast")
    _ok(client.put(f"{S}/{sub_id}/orders/{breakfast.order_id}/skip", headers=w["user_auth"]))
    assert _meal(db, sub_id, TODAY, "breakfast").status == "skipped"
    assert _meal(db, sub_id, TODAY, "lunch").status == "scheduled"
    batch = _ok(client.get(f"{K}/next-batch", headers=w["kitchen_auth"]))["batch"]
    assert batch["meal_slot"] == "lunch" and batch["counts"]["total"] == 1


def test_16_skip_after_assignment_notifies_the_partner(client, db):
    w = f.world(db)
    boy, _ = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _sub_id(client, w)
    meal = _meal(db, sub_id, date(2026, 10, 6))
    assert meal.delivery_boy_reference_id == boy.delivery_boy_id
    _ok(client.put(f"{S}/{sub_id}/orders/{meal.order_id}/skip", headers=w["user_auth"]))
    db.expire_all()
    note = db.query(DeliveryBoyNotification).filter(
        DeliveryBoyNotification.delivery_boy_reference_id == boy.delivery_boy_id,
        DeliveryBoyNotification.title == "Delivery skipped by customer",
    ).one()
    assert note.data["order_id"] == str(meal.order_id)


def test_17_skip_after_cutoff_follows_the_existing_rule(client, db):
    w = f.world(db)
    sub_id = _sub_id(client, w)
    clock.freeze(datetime(2026, 10, 5, 9, 30))  # past the 09:00 lunch cut-off
    meal = _meal(db, sub_id, TODAY)
    listed = _ok(client.get(f"{S}/{sub_id}/orders", headers=w["user_auth"]))["orders"]
    assert next(o for o in listed if o["order_id"] == str(meal.order_id))["skip_will_refund"] is False
    r = _ok(client.put(f"{S}/{sub_id}/orders/{meal.order_id}/skip", headers=w["user_auth"]))
    assert r["refund_amount"] == "0.00" or Decimal(str(r["refund_amount"])) == 0
    assert "cut-off" in r["message"]
    # once the kitchen is cooking, the skip is blocked with a clear reason
    other = _meal(db, sub_id, date(2026, 10, 6))
    other.status = "preparing"
    db.commit()
    blocked = client.put(f"{S}/{sub_id}/orders/{other.order_id}/skip", headers=w["user_auth"])
    assert blocked.status_code == 400 and blocked.json()["code"] == "SKIP_NOT_ALLOWED"
    assert "already started preparing" in blocked.json()["message"]


def _switch(client, w, sub_id, package, kitchen=None, **extra):
    body = {"new_package_id": str(package.package_id), **extra}
    if kitchen is not None:
        body["new_provider_id"] = str(kitchen.provider_id)
    return client.post(f"{S}/{sub_id}/switch", headers=w["user_auth"], json=body)


def test_18_package_switch_shows_new_package_with_tag_from_effective_date(client, db):
    w = f.world(db)
    boy, boy_auth = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _sub_id(client, w)
    new_pkg = f.package(db, w["kitchen"], w["category"], price="200")
    r = _ok(_switch(client, w, sub_id, new_pkg))
    assert r["effective_date"] == "2026-10-06"
    rows = _ok(client.get(f"{D}/orders", headers=boy_auth, params={"from_date": "2026-10-05", "to_date": "2026-10-07"}))["orders"]
    today = next(o for o in rows if o["order_date"] == "2026-10-05")
    tomorrow = next(o for o in rows if o["order_date"] == "2026-10-06" and o["status"] == "scheduled")
    assert "PACKAGE_SWITCHED" not in _tags(today) and today["packages"][0]["package_name"] == w["package"].package_name
    tag = next(t for t in tomorrow["change_tags"] if t["type"] == "PACKAGE_SWITCHED")
    assert tag["from"] == w["package"].package_name and tag["to"] == new_pkg.package_name
    assert tomorrow["packages"][0]["package_name"] == new_pkg.package_name
    krows = _ok(client.get(f"{K}/subscription-orders", headers=w["kitchen_auth"], params={"order_date": "2026-10-06"}))["orders"]
    assert any("PACKAGE_SWITCHED" in _tags(o) and o["packages"][0]["package_name"] == new_pkg.package_name for o in krows)


def test_19_vendor_switch_shows_new_pickup_kitchen_with_tag(client, db):
    w = f.world(db)
    sub_id = _sub_id(client, w)
    other, other_auth = f.provider(db)
    boy, boy_auth = f.delivery_boy(db, kitchen=other)
    pkg_b = f.package(db, other, w["category"], price="180")
    _ok(_switch(client, w, sub_id, pkg_b, other))
    rows = _ok(client.get(f"{D}/orders", headers=boy_auth, params={"order_date": "2026-10-06"}))["orders"]
    assert rows, "the new kitchen's partner gets the meals"
    tag = next(t for t in rows[0]["change_tags"] if t["type"] == "VENDOR_CHANGED")
    assert tag["from"] == w["kitchen"].business_name and tag["to"] == other.business_name
    assert rows[0]["vendor_name"] == other.business_name


def test_20_skip_and_package_switch_on_overlapping_dates(client, db):
    w = f.world(db)
    boy, boy_auth = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _sub_id(client, w)
    new_pkg = f.package(db, w["kitchen"], w["category"], price="200")
    new_sub = _ok(_switch(client, w, sub_id, new_pkg))["new_subscription_id"]
    meal = _meal(db, new_sub, date(2026, 10, 7))
    _ok(client.put(f"{S}/{new_sub}/orders/{meal.order_id}/skip", headers=w["user_auth"]))
    rows = _ok(client.get(f"{D}/orders", headers=boy_auth, params={"order_date": "2026-10-07"}))["orders"]
    row = next(o for o in rows if o["order_id"] == str(meal.order_id))
    assert {"SKIPPED", "PACKAGE_SWITCHED"} <= _tags(row) and row["on_route"] is False
    other_day = next(o for o in _ok(client.get(f"{D}/orders", headers=boy_auth, params={"order_date": "2026-10-08"}))["orders"]
                     if o["status"] == "scheduled")
    assert _tags(other_day) == {"PACKAGE_SWITCHED"}


# ══ Section 6: price breakup ═════════════════════════════════

def test_21_new_subscription_breakup_adds_up_and_is_what_is_charged(client, db):
    w = f.world(db, balance="5000")
    q = _quote(client, w)
    b = q["price_breakup"]
    assert _sum(b) == Decimal(b["total"]) == Decimal("1260.00")
    meals = next(l for l in b["lines"] if l["key"] == "meals_lunch")
    assert meals["meta"]["meals"] == 7 and meals["meta"]["unit_price"] == "180.00"
    assert meals["detail"] == "7 meals × ₹180.00 = ₹1,260.00"
    before = _balance(db, w["user"])
    created = _ok(_subscribe(client, w, expected_total=b["total"]))
    assert before - _balance(db, w["user"]) == Decimal(b["total"])
    assert created["price_breakup"]["total"] == b["total"]
    assert {l["key"] for l in created["price_breakup"]["lines"]} == {l["key"] for l in b["lines"]}


def test_22_discount_named_with_amount_and_percent(client, db):
    w = f.world(db, discount="5")
    b = _quote(client, w)["price_breakup"]
    d = next(l for l in b["lines"] if l["key"] == "discount")
    assert d["meta"]["percent"] == "5.00" or Decimal(d["meta"]["percent"]) == 5
    assert d["meta"]["amount"] == "63.00" and d["amount"] == "-63.00"
    assert d["meta"]["name"] == "Weekly plan discount" and "5% off" in d["label"]
    assert _sum(b) == Decimal(b["total"]) == Decimal("1197.00")


def test_23_every_fee_and_tax_on_its_own_line_with_rates(client, db):
    w = f.world(db)
    _, admin = f.admin(db)
    _price(client, admin, "delivery_charge", value="10", charge_basis="per_delivery")
    _price(client, admin, "packaging_charge", value="5", charge_basis="per_unit")
    _gst(db)
    b = _quote(client, w)["price_breakup"]
    lines = {l["key"]: l for l in b["lines"]}
    assert lines["fee_delivery_charge"]["amount"] == "70.00" and "per delivery" in lines["fee_delivery_charge"]["detail"]
    assert lines["fee_packaging_charge"]["amount"] == "35.00"
    assert lines["tax_gst"]["label"] == "GST 5%" and lines["tax_gst"]["amount"] == "63.00"
    assert "fee_platform_commission" in lines and lines["fee_platform_commission"]["amount"] == "0.00"
    assert _sum(b) == Decimal(b["total"]) == Decimal("1428.00")


def _switch_preview(client, w, sub_id, package, kitchen=None):
    body = {"new_package_id": str(package.package_id)}
    if kitchen is not None:
        body["new_provider_id"] = str(kitchen.provider_id)
    return _ok(client.post(f"{S}/{sub_id}/switch/preview", headers=w["user_auth"], json=body))


def test_24_switch_to_a_more_expensive_kitchen(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    other, _ = f.provider(db)
    pkg_b = f.package(db, other, w["category"], price="200")
    p = _switch_preview(client, w, sub_id, pkg_b, other)
    b = p["price_breakup"]
    lines = {l["key"]: l for l in b["lines"]}
    assert b["kind"] == "vendor_switch" and p["vendor_changed"] is True
    assert lines["already_paid"]["amount"] == "1260.00"
    assert lines["meals_used"]["meta"]["meals"] == 1
    assert lines["remaining_value"]["amount"] == "-1080.00"  # 6 meals x 180
    assert b["new_plan_cost"] == "1200.00" and b["difference"] == "120.00"
    assert b["total"] == "120.00" and _sum(b) == Decimal("120.00") and b["refund"] is None
    before = _balance(db, w["user"])
    _ok(_switch(client, w, sub_id, pkg_b, other, expected_total=b["total"]))
    assert before - _balance(db, w["user"]) == Decimal("120.00")


def test_25_switch_to_a_cheaper_kitchen_refunds_to_the_wallet(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    other, _ = f.provider(db)
    pkg_b = f.package(db, other, w["category"], price="150")
    b = _switch_preview(client, w, sub_id, pkg_b, other)["price_breakup"]
    assert b["total"] == "-180.00" and _sum(b) == Decimal("-180.00")
    assert b["refund"] == {"amount": "180.00", "destination": "wallet", "when": price_breakup.REFUND_WHEN}
    before = _balance(db, w["user"])
    _ok(_switch(client, w, sub_id, pkg_b, other, expected_total=b["total"]))
    assert _balance(db, w["user"]) - before == Decimal("180.00")


def test_26_package_upgrade_and_downgrade_breakups(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    up = f.package(db, w["kitchen"], w["category"], price="210")
    down = f.package(db, w["kitchen"], w["category"], price="160")
    b_up = _switch_preview(client, w, sub_id, up)["price_breakup"]
    b_down = _switch_preview(client, w, sub_id, down)["price_breakup"]
    assert b_up["kind"] == "package_switch" and b_up["total"] == "180.00" and _sum(b_up) == Decimal("180.00")
    assert b_down["total"] == "-120.00" and _sum(b_down) == Decimal("-120.00")
    assert b_down["refund"]["amount"] == "120.00"


def test_27_amount_charged_equals_amount_shown_for_a_one_time_order(client, db):
    w = f.world(db, balance="1000")
    _, admin = f.admin(db)
    _price(client, admin, "delivery_charge", value="25", charge_basis="per_delivery")
    body = {"vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
            "delivery_date": "2026-10-06", "meal_slot": "lunch",
            "items": [{"package_id": str(w["package"].package_id), "quantity": 2}]}
    q = _ok(client.post(f"{API}/user/order/extra/quote", headers=w["user_auth"], json=body))
    b = q["price_breakup"]
    assert _sum(b) == Decimal(b["total"]) == Decimal("385.00")
    before = _balance(db, w["user"])
    placed = _ok(client.post(f"{API}/user/order/extra", headers=w["user_auth"], json={**body, "expected_total": b["total"]}))
    assert before - _balance(db, w["user"]) == Decimal(b["total"]) == Decimal(str(placed["total_amount"]))


def test_28_price_change_between_view_and_pay_needs_a_new_confirmation(client, db):
    w = f.world(db, balance="5000")
    _, admin = f.admin(db)
    shown = _quote(client, w)["price_breakup"]
    _price(client, admin, "delivery_charge", value="10", charge_basis="per_delivery")
    before = _balance(db, w["user"])
    r = _subscribe(client, w, expected_total=shown["total"])
    assert r.status_code == 409 and r.json()["code"] == "PRICE_CHANGED"
    fresh = r.json()["price_breakup"]
    assert fresh["total"] == "1330.00" and _sum(fresh) == Decimal("1330.00")
    assert _balance(db, w["user"]) == before and db.query(Subscription).count() == 0
    _ok(_subscribe(client, w, expected_total=fresh["total"]))
    assert before - _balance(db, w["user"]) == Decimal("1330.00")


def test_29_rounding_never_loses_or_adds_a_paisa(client, db):
    w = f.world(db, price="99.99", balance="5000")
    _gst(db)
    b = _quote(client, w)["price_breakup"]
    lines = {l["key"]: l for l in b["lines"]}
    assert lines["meals_lunch"]["amount"] == "699.93"
    assert lines["tax_gst"]["amount"] == "35.00"  # 34.9965 rounded half-up once
    assert b["total"] == "734.93" and _sum(b) == Decimal("734.93")
    before = _balance(db, w["user"])
    _ok(_subscribe(client, w, expected_total=b["total"]))
    assert before - _balance(db, w["user"]) == Decimal("734.93")


def test_30_wallet_covers_partly_or_fully(client, db):
    w = f.world(db, balance="300")
    part = _quote(client, w)["price_breakup"]
    assert part["wallet_applied"] == "300.00" and part["amount_payable"] == "960.00"
    user, address, auth = f.customer(db, balance="5000")
    full = _quote(client, {**w, "user_auth": auth, "address": address})["price_breakup"]
    assert full["wallet_applied"] == "1260.00" and full["amount_payable"] == "0.00"
    assert full["wallet_balance_after"] == "3740.00"


# ══ Section 7: holiday pricing ═══════════════════════════════

def _holiday(client, w, **rule):
    return _ok(client.post(H, headers=w["kitchen_auth"], json=rule))


def test_31_sundays_closed_not_charged_listed_and_meal_count_kept(client, db):
    w = f.world(db, balance="5000")
    _holiday(client, w, preset="every_sunday")
    q = _quote(client, w)
    b = q["price_breakup"]
    holiday = next(l for l in b["lines"] if l["key"] == "vendor_holidays")
    assert holiday["amount"] == "0.00" and holiday["meta"]["dates"] == ["2026-10-11"]
    assert b["total"] == "1260.00" and b["meals"] == 7
    assert q["end_date"] == "2026-10-13"
    sub_id = _sub_id(client, w)
    meals = _meals(db, sub_id)
    assert len(meals) == 7 and all(m.order_date.isoweekday() != 7 for m in meals)
    assert db.get(Subscription, uuid.UUID(sub_id)).holiday_dates == ["2026-10-11"]


def test_32_switch_into_a_kitchen_with_holidays_excludes_them_from_the_price(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    other, other_auth = f.provider(db)
    pkg_b = f.package(db, other, w["category"], price="180")
    _ok(client.post(H, headers=other_auth, json={"rule_type": "dates", "dates": ["2026-10-08"]}))
    b = _switch_preview(client, w, sub_id, pkg_b, other)["price_breakup"]
    assert b["holiday_dates"] == ["2026-10-08"] and b["meals"] == 6
    assert next(l for l in b["lines"] if l["key"] == "vendor_holidays")["amount"] == "0.00"
    new_sub = _ok(_switch(client, w, sub_id, pkg_b, other))["new_subscription_id"]
    days = {m.order_date for m in _meals(db, new_sub)}
    assert date(2026, 10, 8) not in days and len(days) == 6 and max(days) == date(2026, 10, 12)


def test_33_new_casual_holiday_replans_existing_subscriptions(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    before = _balance(db, w["user"])
    r = _holiday(client, w, rule_type="dates", dates=["2026-10-07"])
    assert r["affected_subscriptions"] == 1
    db.expire_all()
    sub = db.get(Subscription, uuid.UUID(sub_id))
    assert sub.end_date == date(2026, 10, 13) and sub.holiday_dates == ["2026-10-07"]
    assert _meal(db, sub_id, date(2026, 10, 7)).cancel_reason == "vendor_holiday"
    assert len([m for m in _meals(db, sub_id) if m.status == "scheduled"]) == 7  # no paid meal lost
    assert _balance(db, w["user"]) == before
    note = db.query(Notification).filter(Notification.type == "vendor_holiday").one()
    assert "no charge" in note.body and note.data["new_end_date"] == "2026-10-13"


# ══ Sections 8.2-8.3: casual holidays ════════════════════════

def _rule(**kw) -> VendorHoliday:
    return VendorHoliday(provider_reference_id=uuid.uuid4(), holiday_type="casual", **kw)


def test_34_every_sunday_across_month_year_and_leap_day(db):
    sundays = holidays.rule_dates(_rule(rule_type="weekly", weekdays=[7], start_date=date(2027, 12, 20)),
                                  date(2027, 12, 20), date(2028, 1, 10))
    assert sorted(sundays) == [date(2027, 12, 26), date(2028, 1, 2), date(2028, 1, 9)]
    feb = holidays.rule_dates(_rule(rule_type="weekly", weekdays=[2], start_date=date(2028, 2, 1)),
                              date(2028, 2, 26), date(2028, 3, 2))
    assert feb == {date(2028, 2, 29)}  # leap day is a Tuesday
    monthly = _rule(rule_type="monthly", month_days=[29], start_date=date(2027, 1, 1))
    assert holidays.rule_dates(monthly, date(2027, 2, 1), date(2027, 2, 28)) == set()
    assert holidays.rule_dates(monthly, date(2028, 2, 1), date(2028, 2, 29)) == {date(2028, 2, 29)}


def test_35_every_kind_of_casual_rule(client, db):
    w = f.world(db)
    cases = [
        ({"preset": "weekends"}, {date(2026, 10, 10), date(2026, 10, 11)}),
        ({"rule_type": "weekly", "weekdays": [1, 3]}, {date(2026, 10, 7), date(2026, 10, 12)}),
        ({"rule_type": "dates", "dates": ["2026-10-09"]}, {date(2026, 10, 9)}),
        ({"rule_type": "range", "start_date": "2026-10-20", "end_date": "2026-10-22"},
         {date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)}),
        ({"rule_type": "monthly", "month_days": [15]}, {date(2026, 10, 15)}),
    ]
    for body, expected in cases:
        created = _holiday(client, w, **body)["holiday"]
        h = db.get(VendorHoliday, uuid.UUID(created["holiday_id"]))
        got = holidays.rule_dates(h, date(2026, 10, 6), date(2026, 10, 22))
        assert expected <= got and created["label"].startswith("Closed")
    overview = _ok(client.get(H, headers=w["kitchen_auth"]))
    assert overview["weekly_holiday_set"] is True
    assert "Closed every Saturday and Sunday" in overview["regular_holidays"]


def test_36_future_holidays_edit_and_remove_past_ones_do_not(client, db):
    w = f.world(db)
    h = _holiday(client, w, rule_type="dates", dates=["2026-10-09"])["holiday"]
    edited = _ok(client.put(f"{H}/rules/{h['holiday_id']}", headers=w["kitchen_auth"],
                            json={"rule_type": "dates", "dates": ["2026-10-10"]}))
    assert edited["holiday"]["dates"] == ["2026-10-10"]
    _ok(client.delete(f"{H}/rules/{h['holiday_id']}", headers=w["kitchen_auth"]))
    assert not holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 10))
    past = VendorHoliday(provider_reference_id=w["kitchen"].provider_id, holiday_type="casual", rule_type="dates",
                         dates=[date(2026, 10, 1)], start_date=date(2026, 10, 1), end_date=date(2026, 10, 1))
    db.add(past)
    db.commit()
    for r in (client.put(f"{H}/rules/{past.vendor_holiday_id}", headers=w["kitchen_auth"],
                         json={"rule_type": "dates", "dates": ["2026-10-12"]}),
              client.delete(f"{H}/rules/{past.vendor_holiday_id}", headers=w["kitchen_auth"])):
        assert r.status_code == 400 and r.json()["code"] == "HOLIDAY_IN_PAST"
    started = _holiday(client, w, preset="every_sunday")["holiday"]
    clock.freeze(datetime(2026, 10, 11, 5, 0))  # the rule is already closing its first Sunday
    _ok(client.put(f"{H}/rules/{started['holiday_id']}", headers=w["kitchen_auth"], json={"preset": "weekends"}))
    db.expire_all()
    old = db.get(VendorHoliday, uuid.UUID(started["holiday_id"]))
    assert old.end_date == date(2026, 10, 11)  # the day already started stays on record
    assert holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 11))
    assert holidays.is_closed(db, w["kitchen"].provider_id, date(2026, 10, 17))


def test_37_duplicate_and_overlapping_holidays_never_double_process(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    _holiday(client, w, preset="every_sunday")
    dup = client.post(H, headers=w["kitchen_auth"], json={"preset": "every_sunday"})
    assert dup.status_code == 409 and dup.json()["code"] == "HOLIDAY_EXISTS"
    same_day = client.post(H, headers=w["kitchen_auth"], json={"rule_type": "dates", "dates": ["2026-10-11"]})
    assert same_day.status_code == 409
    db.expire_all()
    sub = db.get(Subscription, uuid.UUID(sub_id))
    assert sub.end_date == date(2026, 10, 13) and sub.holiday_dates == ["2026-10-11"]
    assert db.query(Notification).filter(Notification.type == "vendor_holiday").count() == 1
    assert len([m for m in _meals(db, sub_id) if m.status == "scheduled"]) == 7


def test_38_daily_generation_creates_no_meal_on_a_holiday(client, db):
    w = f.world(db, balance="5000", plan_days=14)
    sub_id = _sub_id(client, w)
    # a holiday the subscription has not planned around yet, on dates without meals
    db.query(Order).filter(Order.subscription_reference_id == sub_id, Order.order_date >= date(2026, 10, 12)).delete()
    db.add(VendorHoliday(provider_reference_id=w["kitchen"].provider_id, holiday_type="casual", rule_type="dates",
                         dates=[date(2026, 10, 14)], start_date=date(2026, 10, 14), end_date=date(2026, 10, 14)))
    db.commit()
    jobs.generate_meals_job()
    meals = _meals(db, sub_id)
    assert date(2026, 10, 14) not in {m.order_date for m in meals}
    assert len(meals) == 14
    assert db.get(Subscription, uuid.UUID(sub_id)).end_date == date(2026, 10, 20)


def test_39_holidays_are_shown_to_customers(client, db):
    w = f.world(db, balance="5000")
    _holiday(client, w, preset="every_sunday")
    _holiday(client, w, rule_type="dates", dates=["2026-10-08"])
    listing = _ok(client.get(f"{API}/user/menu/packages", headers=w["user_auth"], params={"pin_code": f.PIN}))
    view = listing["packages"][0]["vendor_holidays"]
    assert view["regular_holidays"] == ["Closed every Sunday"]
    assert [u["date"] for u in view["upcoming_holidays"]][:2] == ["2026-10-08", "2026-10-11"]
    sub_id = _sub_id(client, w)
    cal = _ok(client.get(f"{S}/{sub_id}/orders", headers=w["user_auth"]))
    assert [h["date"] for h in cal["holiday_dates"]] == ["2026-10-08", "2026-10-11"]
    assert cal["holiday_dates"][0]["label"] == "Vendor holiday – no delivery"
    detail = _ok(client.get(f"{S}/{sub_id}", headers=w["user_auth"]))
    assert detail["holiday_dates"] == ["2026-10-08", "2026-10-11"]
    assert detail["vendor_holidays"]["holiday_summary"] == "Closed every Sunday"


def test_40_near_midnight_ist_lands_on_the_ist_date(client, db):
    w = f.world(db)
    clock.freeze(datetime(2026, 10, 5, 23, 59))  # 18:29 UTC
    assert _ok(client.post(H, headers=w["kitchen_auth"], json={"rule_type": "dates", "dates": ["2026-10-06"]}))
    e = _ok(client.post(f"{H}/emergency", headers=w["kitchen_auth"], json={}))
    assert e["holiday"]["start_date"] == "2026-10-05"
    other, other_auth = f.provider(db)
    clock.freeze(datetime(2026, 10, 6, 0, 1))  # still 5 Oct in UTC
    assert _ok(client.post(f"{H}/emergency", headers=other_auth, json={}))["holiday"]["start_date"] == "2026-10-06"
    late = client.post(H, headers=other_auth, json={"rule_type": "dates", "dates": ["2026-10-06"]})
    assert late.status_code == 400 and late.json()["code"] == "HOLIDAY_IN_PAST"


# ══ Section 8.4: emergency holidays ══════════════════════════

def _emergency(client, w, day=None, reason="gas leak"):
    body = {"reason": reason}
    if day:
        body["date"] = day
    return client.post(f"{H}/emergency", headers=w["kitchen_auth"], json=body)


def _replacement(db, w, *, price="150", pin=f.PIN, meal_type="lunch", food_type="veg", capacity=None, quota=None,
                 same_package=False):
    kitchen, auth = f.provider(db, pin=pin, quota=quota)
    if same_package:
        f.offer(db, kitchen, w["package"], capacity=capacity)
        return kitchen, w["package"]
    pkg = f.package(db, kitchen, w["category"], price=price, meal_type=meal_type, food_type=food_type,
                    capacity=capacity)
    return kitchen, pkg


def test_41_emergency_with_no_affected_meals(client, db):
    w = f.world(db)
    r = _ok(_emergency(client, w))
    assert r["holiday"]["affected_meals"] == 0 and r["holiday"]["processing_status"] == "completed"
    assert db.query(Notification).count() == 0


def test_42_past_date_is_rejected(client, db):
    w = f.world(db)
    r = _emergency(client, w, day="2026-10-04")
    assert r.status_code == 400 and r.json()["code"] == "HOLIDAY_IN_PAST"


def test_43_replacement_found_meal_moves_user_told_delivery_side_updated(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    kitchen_b, pkg_b = _replacement(db, w, price="160")
    boy_b, boy_b_auth = f.delivery_boy(db, kitchen=kitchen_b)
    before = _balance(db, w["user"])
    r = _ok(_emergency(client, w))
    assert r["holiday"]["replaced_meals"] == 1
    meal = _meal(db, sub_id, TODAY)
    assert meal.vendor_reference_id == kitchen_b.provider_id
    assert meal.original_vendor_reference_id == w["kitchen"].provider_id
    assert meal.replacement_package_reference_id == pkg_b.package_id
    assert meal.delivery_boy_reference_id == boy_b.delivery_boy_id and meal.status == "scheduled"
    note = db.query(Notification).filter(Notification.type == "vendor_holiday_replacement").one()
    assert note.body == (
        "Sorry for the inconvenience! Your regular vendor is unavailable today due to an emergency. "
        f"We have arranged your meal from {kitchen_b.business_name} at no extra cost. "
        "Your meal will be delivered as scheduled."
    )
    assert _balance(db, w["user"]) == before  # no extra charge
    row = _ok(client.get(f"{D}/orders", headers=boy_b_auth))["orders"][0]
    tag = next(t for t in row["change_tags"] if t["type"] == "VENDOR_CHANGED")
    assert tag["to"] == kitchen_b.business_name and row["packages"][0]["package_name"] == pkg_b.package_name
    # the other days stay with the regular kitchen
    assert _meal(db, sub_id, date(2026, 10, 6)).vendor_reference_id == w["kitchen"].provider_id


@pytest.mark.parametrize("price, outcome", [("150", "replaced"), ("180", "replaced"), ("180.01", "compensated")])
def test_44_45_46_replacement_price_must_not_exceed_the_subscribed_price(client, db, price, outcome):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    _replacement(db, w, price=price)
    _ok(_emergency(client, w))
    rec = db.query(VendorHolidayMeal).one()
    assert rec.outcome == outcome
    if outcome == "replaced":
        assert rec.replacement_meal_price <= rec.original_meal_price
    else:
        assert _meal(db, sub_id, TODAY).cancel_reason == "vendor_emergency_holiday"


def _assert_compensated(db, sub_id):
    rec = db.query(VendorHolidayMeal).one()
    assert rec.outcome == "compensated", rec.last_error
    assert _meal(db, sub_id, TODAY).status == "cancelled"
    return rec


def test_47_replacement_in_another_pin_code_is_rejected(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    f.pincode(db, 560002)
    _replacement(db, w, pin=560002)
    _ok(_emergency(client, w))
    _assert_compensated(db, sub_id)


def test_48_replacement_on_holiday_is_rejected(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    kitchen_b, _ = _replacement(db, w)
    db.add(VendorHoliday(provider_reference_id=kitchen_b.provider_id, holiday_type="casual", rule_type="dates",
                         dates=[TODAY], start_date=TODAY, end_date=TODAY))
    db.commit()
    _ok(_emergency(client, w))
    _assert_compensated(db, sub_id)


@pytest.mark.parametrize("meal_type, food_type", [("dinner", "veg"), ("lunch", "non_veg")])
def test_49_replacement_without_the_meal_type_or_diet_is_rejected(client, db, meal_type, food_type):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    _replacement(db, w, meal_type=meal_type, food_type=food_type)
    _ok(_emergency(client, w))
    _assert_compensated(db, sub_id)


def test_50_replacement_without_capacity_is_rejected(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    kitchen_b, pkg_b = _replacement(db, w, capacity=1)
    # another customer already took the replacement kitchen's only lunch today
    _ok(client.post(f"{API}/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(kitchen_b.provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-05", "meal_slot": "lunch",
        "items": [{"package_id": str(pkg_b.package_id), "quantity": 1}],
    }))
    _ok(_emergency(client, w))
    assert "no capacity" in _assert_compensated(db, sub_id).last_error


def test_50_replacement_that_cannot_make_the_time_slot_is_rejected(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    _replacement(db, w)
    clock.freeze(datetime(2026, 10, 5, 12, 30))  # the lunch delivery window has begun
    _ok(_emergency(client, w))
    assert "time slot" in _assert_compensated(db, sub_id).last_error


def test_51_several_replacements_same_deterministic_choice(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    first, _ = _replacement(db, w, price="150")
    second, _ = _replacement(db, w, price="150")
    sub = db.get(Subscription, uuid.UUID(sub_id))
    meal = _meal(db, sub_id, TODAY)
    picks = {str(emergency_holiday.candidates(db, meal, sub)[0][0]["provider"].provider_id) for _ in range(3)}
    assert picks == {min(str(first.provider_id), str(second.provider_id))}
    # a kitchen selling the very same package wins over one selling a similar package
    same, _ = _replacement(db, w, same_package=True)
    assert emergency_holiday.candidates(db, meal, sub)[0][0]["provider"].provider_id == same.provider_id
    _ok(_emergency(client, w))
    assert _meal(db, sub_id, TODAY).vendor_reference_id == same.provider_id


def test_52_53_54_no_replacement_one_skip_and_the_meal_value_as_two_entries(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    before = _balance(db, w["user"])
    _ok(_emergency(client, w))
    rec = _assert_compensated(db, sub_id)
    skip = db.query(SkipCreditTransaction).one()
    assert skip.skips == 1 and skip.reason == "VENDOR_EMERGENCY_HOLIDAY_COMPENSATION"
    assert skip.order_reference_id == rec.order_reference_id and skip.vendor_reference_id == w["kitchen"].provider_id
    assert skip.meal_date == TODAY and skip.reference_id == rec.vendor_holiday_reference_id
    sub = db.get(Subscription, uuid.UUID(sub_id))
    assert sub.free_skips_total == 3  # plan's 2 + the gift
    refund = db.query(WalletTransaction).filter(WalletTransaction.reason == "VENDOR_EMERGENCY_HOLIDAY_MEAL_REFUND").one()
    assert refund.amount == Decimal("180.00") and refund.reference_id == rec.order_reference_id
    assert _balance(db, w["user"]) - before == Decimal("180.00")
    assert rec.wallet_transaction_reference_id == refund.wallet_transaction_id
    assert rec.skip_credit_reference_id == skip.skip_credit_transaction_id


def test_55_retrying_creates_no_duplicates(client, db):
    w = f.world(db, balance="5000")
    _sub_id(client, w)
    _, admin = f.admin(db)
    hid = _ok(_emergency(client, w))["holiday"]["holiday_id"]
    counts = lambda: (db.query(SkipCreditTransaction).count(), db.query(WalletTransaction).count(),  # noqa: E731
                      db.query(Notification).count(), db.query(Order).count())
    first = counts()
    emergency_holiday.process(db, uuid.UUID(hid))
    _ok(client.post(f"{API}/admin/holidays/{hid}/retry", headers=admin))
    db.expire_all()
    assert counts() == first


def test_56_already_delivered_meal_is_not_compensated(client, db):
    w = f.world(db, balance="5000")
    boy_auth, meal = _picked_up(client, db, w)
    _ok(client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": f.delivery_code(meal)}))
    r = _ok(_emergency(client, w))
    assert r["holiday"]["affected_meals"] == 0
    assert db.query(SkipCreditTransaction).count() == 0


def test_57_customer_skip_on_that_date_is_not_compensated(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    meal = _meal(db, sub_id, TODAY)
    _ok(client.put(f"{S}/{sub_id}/orders/{meal.order_id}/skip", headers=w["user_auth"]))
    refunds = db.query(WalletTransaction).filter(WalletTransaction.reason != "adjustment").count()
    assert _ok(_emergency(client, w))["holiday"]["affected_meals"] == 0
    db.expire_all()
    assert db.query(SkipCreditTransaction).count() == 0
    assert db.query(WalletTransaction).filter(WalletTransaction.reason != "adjustment").count() == refunds


def test_58_failed_notice_is_retried_without_repeating_money(client, db, monkeypatch):
    w = f.world(db, balance="5000")
    _sub_id(client, w)
    real = notify.customer

    def broken(*args, **kwargs):
        raise RuntimeError("push service down")

    monkeypatch.setattr(notify, "customer", broken)
    hid = _ok(_emergency(client, w))["holiday"]["holiday_id"]
    db.expire_all()
    rec = db.query(VendorHolidayMeal).one()
    assert rec.compensation_status == "completed" and rec.notification_status == "failed"
    money = (db.query(WalletTransaction).count(), db.query(SkipCreditTransaction).count())
    monkeypatch.setattr(notify, "customer", real)
    assert emergency_holiday.send_notifications(db, uuid.UUID(hid)) == {"sent": 1, "failed": 0}
    assert emergency_holiday.send_notifications(db, uuid.UUID(hid)) == {"sent": 0, "failed": 0}
    db.expire_all()
    assert (db.query(WalletTransaction).count(), db.query(SkipCreditTransaction).count()) == money
    note = db.query(Notification).filter(Notification.type == "vendor_holiday_compensation").one()
    assert "credited ₹180.00 for today's meal" in note.body
    assert db.query(VendorHolidayMeal).one().notification_status == "sent"


def test_59_concurrent_processing_assigns_a_meal_once(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    _replacement(db, w, price="150")
    _replacement(db, w, price="150")
    holiday = emergency_holiday.declare(db, w["kitchen"].provider_id, TODAY, "flood", actor_type="provider",
                                        actor_id=w["kitchen"].provider_id)
    rid = db.query(VendorHolidayMeal.vendor_holiday_meal_id).filter(
        VendorHolidayMeal.vendor_holiday_reference_id == holiday.vendor_holiday_id).scalar()
    outcomes, errors = [], []

    def run():
        session = SessionLocal()
        try:
            outcomes.append(emergency_holiday.process_meal(session, rid))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and outcomes == ["replaced"] * 4
    db.expire_all()
    rec = db.query(VendorHolidayMeal).one()
    assert rec.attempts == 1
    assert _meal(db, sub_id, TODAY).vendor_reference_id == rec.replacement_vendor_reference_id


def test_60_closed_kitchen_gets_nothing_new_that_day(client, db):
    w = f.world(db, balance="5000")
    _ok(_emergency(client, w))
    r = client.post(f"{API}/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-05", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 400 and r.json()["code"] == "KITCHEN_HOLIDAY"
    sub_id = _sub_id(client, w)
    assert TODAY not in {m.order_date for m in _meals(db, sub_id)}
    assert db.get(Subscription, uuid.UUID(sub_id)).holiday_dates == ["2026-10-05"]


def test_61_subscription_and_billing_continue_after_the_holiday(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    sub = db.get(Subscription, uuid.UUID(sub_id))
    end, paid = sub.end_date, sub.final_amount
    _ok(_emergency(client, w))
    db.expire_all()
    sub = db.get(Subscription, uuid.UUID(sub_id))
    assert sub.status == "active" and sub.end_date == end and sub.final_amount == paid
    tomorrow = _meal(db, sub_id, date(2026, 10, 6))
    assert tomorrow.status == "scheduled" and tomorrow.vendor_reference_id == w["kitchen"].provider_id
    assert db.query(WalletTransaction).filter(WalletTransaction.reason == "subscription_payment").count() == 1


# ══ End to end ═══════════════════════════════════════════════

def test_62_subscribe_prepare_from_home_bulk_ready_pickup_deliver(client, db):
    w = f.world(db, balance="5000")
    boy, boy_auth = f.delivery_boy(db, kitchen=w["kitchen"])
    quote = _quote(client, w)["price_breakup"]
    sub_id = _ok(_subscribe(client, w, expected_total=quote["total"]))["subscription_id"]
    batch = _ok(client.get(f"{K}/next-batch", headers=w["kitchen_auth"]))["batch"]
    _ok(client.put(f"{K}/batch/status", headers=w["kitchen_auth"],
                   json={"order_date": batch["date"], "meal_slot": batch["meal_slot"], "status": "preparing"}))
    assert _ok(client.get(f"{K}/ready-today", headers=w["kitchen_auth"]))["eligible"] == 1
    _ok(client.post(f"{K}/ready-today", headers=w["kitchen_auth"], json={"expected_count": 1}))
    meal = _meal(db, sub_id, TODAY)
    _ok(client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_auth,
                   json={"pickup_code": f.pickup_code(db, w["kitchen"])}))
    done = _ok(client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_auth, json={"otp": f.delivery_code(meal)}))
    assert done["status"] == "delivered"
    assert _meal(db, sub_id, TODAY).status == "delivered"


def test_63_emergency_replacement_delivered_by_the_new_kitchen(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    kitchen_b, pkg_b = _replacement(db, w, price="170")
    boy_b, boy_b_auth = f.delivery_boy(db, kitchen=kitchen_b)
    _ok(_emergency(client, w))
    kb_auth = f.auth(__import__("app.core.security", fromlist=["x"]).create_access_token(
        {"provider_id": str(kitchen_b.provider_id)}, role="provider", token_version=0))
    batch = _ok(client.get(f"{K}/next-batch", headers=kb_auth))["batch"]
    assert batch["item_summary"] == [{"package_name": pkg_b.package_name, "quantity": 1}]
    _ok(client.post(f"{K}/ready-today", headers=kb_auth))
    row = _ok(client.get(f"{D}/orders", headers=boy_b_auth))["orders"][0]
    assert "VENDOR_CHANGED" in _tags(row) and row["vendor_name"] == kitchen_b.business_name
    meal = _meal(db, sub_id, TODAY)
    _ok(client.put(f"{D}/orders/{meal.order_id}/pickup", headers=boy_b_auth,
                   json={"pickup_code": f.pickup_code(db, kitchen_b)}))
    _ok(client.put(f"{D}/orders/{meal.order_id}/deliver", headers=boy_b_auth, json={"otp": f.delivery_code(meal)}))
    assert _meal(db, sub_id, TODAY).status == "delivered"


def test_64_emergency_without_replacement_user_credits_and_not_deliverable(client, db):
    w = f.world(db, balance="5000")
    boy, boy_auth = f.delivery_boy(db, kitchen=w["kitchen"])
    sub_id = _sub_id(client, w)
    _ok(_emergency(client, w))
    notes = _ok(client.get(f"{API}/user/notification", headers=w["user_auth"]))
    items = notes.get("notifications") or notes.get("items") or []
    assert any(n["type"] == "vendor_holiday_compensation" for n in items)
    detail = _ok(client.get(f"{S}/{sub_id}", headers=w["user_auth"]))
    assert detail["free_skips_total"] == 3
    meals = _ok(client.get(f"{S}/{sub_id}/orders", headers=w["user_auth"]))["orders"]
    today = next(m for m in meals if m["order_date"] == "2026-10-05")
    assert today["holiday_outcome"]["outcome"] == "compensated" and today["holiday_outcome"]["skips_credited"] == 1
    row = next(o for o in _ok(client.get(f"{D}/orders", headers=boy_auth))["orders"] if o["order_date"] == "2026-10-05")
    assert "NOT_DELIVERABLE_VENDOR_HOLIDAY" in _tags(row) and row["on_route"] is False
    assert row["change_tags"][0]["label"] == "NOT DELIVERABLE – VENDOR HOLIDAY"
    admin_view = _ok(client.get(f"{API}/admin/holidays/meals", headers=f.admin(db)[1], params={"outcome": "compensated"}))
    assert admin_view["total"] == 1 and Decimal(str(admin_view["meals"][0]["meal_amount"])) == Decimal("180.00")


def test_breakup_invariant_holds_for_many_prices(db):
    """Property check: lines always add up to the total, whatever the inputs."""
    from app.domain.pricing import build_quote
    from app.models.pricing_component_model import PricingComponent

    comps = [
        PricingComponent(component_key="delivery_charge", label="Delivery", calc_type="fixed", value=Decimal("7.37"),
                         applies_to="all", charge_basis="per_delivery", is_customer_facing=True, is_active=True, version=1),
        PricingComponent(component_key="gst", label="GST", calc_type="percentage", value=Decimal("5"),
                         applies_to="all", charge_basis="per_order", is_customer_facing=True, is_active=True, version=1),
    ]
    for unit in ("99.99", "0.01", "123.45", "180", "77.77"):
        for meals in (1, 7, 13, 30):
            for pct in ("0", "5", "7.5", "12.25"):
                snap = build_quote(comps, kind="subscription", base_unit_price=Decimal(unit), quantity=1,
                                   deliveries=meals, discount_percent=pct)
                b = price_breakup.subscription(snap, slots=["lunch"], package_name="P", plan_name="X",
                                               holiday_dates=[date(2026, 10, 11)], wallet_balance="50")
                assert _sum(b) == Decimal(b["total"]) == Decimal(snap["total_payable"])
                assert Decimal(b["wallet_applied"]) + Decimal(b["amount_payable"]) == Decimal(b["total"])
