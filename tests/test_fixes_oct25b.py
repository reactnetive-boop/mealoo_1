"""
Fixes of 25 Oct 2026 (second round): item quantity restored without units,
kitchen may start / pack meals at any time, exact-paisa wallet credits,
price breakup on every screen (package detail, one-time order lines, older
plans, admin), customer withdrawals off.

Clock: Monday 5 Oct 2026, 05:00 IST (tests/conftest.py).
"""

import uuid
from datetime import date
from decimal import Decimal

from app.models.menu_package_item_model import MenuPackageItem
from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.models.wallet_model import Wallet
from app.models.wallet_transaction_model import WalletTransaction
from tests import factories as f
from tests.test_mealoo_oct25 import API, K, S, TODAY, _meal, _ok, _sub_id, _sum, _switch, _switch_preview

TOMORROW = date(2026, 10, 6)


def _balance(db, user) -> Decimal:
    db.expire_all()
    return db.query(Wallet).filter(Wallet.user_reference_id == user.user_id).one().balance


def _create_package(client, w, items):
    return _ok(client.post(f"{API}/menu/package", headers=w["kitchen_auth"], json={
        "category_id": str(w["category"].category_id), "package_name": "Roti Thali", "meal_type": ["lunch"],
        "food_type": "veg", "price": "150", "is_subscription_available": True, "subscription_price": "150",
        "items": items,
    }))


# ══ Bug 1: item quantity (a count, no unit) ═══════════════════

def test_quantity_is_saved_and_returned_everywhere(client, db):
    w = f.world(db)
    pkg = _create_package(client, w, [{"item_name": "Roti", "quantity_value": 4}, {"item_name": "Dal", "quantity_value": "1"}])
    rows = {i.item_name: i for i in db.query(MenuPackageItem).filter(MenuPackageItem.package_reference_id == pkg["package_id"])}
    assert rows["Roti"].quantity == "4" and rows["Roti"].quantity_value == Decimal("4") and rows["Roti"].quantity_unit is None

    kitchen_view = _ok(client.get(f"{API}/menu/get/{pkg['package_id']}", headers=w["kitchen_auth"]))
    items = kitchen_view.get("items") or kitchen_view.get("package", {}).get("items")
    assert {i["item_name"]: i["quantity_count"] for i in items} == {"Roti": 4, "Dal": 1}

    _, admin = f.admin(db)
    admin_view = _ok(client.get(f"{API}/admin/packages/{pkg['package_id']}", headers=admin))
    admin_items = admin_view.get("items") or admin_view.get("package", {}).get("items")
    assert {i["item_name"]: i["quantity_count"] for i in admin_items} == {"Roti": 4, "Dal": 1}


def test_quantity_is_validated(client, db):
    w = f.world(db)
    pkg = _create_package(client, w, [{"item_name": "Dal", "quantity_value": 1}])  # not live yet: edits apply at once
    for bad in (0, 1000, "2.5", -3):
        r = client.post(f"{API}/package/item/add", headers=w["kitchen_auth"],
                        json={"package_id": pkg["package_id"], "item_name": "Roti", "quantity_value": bad})
        assert r.status_code == 422, (bad, r.text)
    r = _ok(client.post(f"{API}/package/item/add", headers=w["kitchen_auth"],
                        json={"package_id": pkg["package_id"], "item_name": "Roti", "quantity_value": 3}))
    item_id = r["item_id"]
    _ok(client.put(f"{API}/package/item/update/{item_id}", headers=w["kitchen_auth"], json={"quantity_value": 5}))
    db.expire_all()
    assert db.query(MenuPackageItem).filter(MenuPackageItem.item_id == item_id).one().quantity == "5"


def test_customer_sees_counts_and_food_summary_totals_them(client, db):
    w = f.world(db)
    db.add_all([
        MenuPackageItem(package_reference_id=w["package"].package_id, item_name="Roti", quantity="4",
                        quantity_value=Decimal("4"), item_order=1),
        MenuPackageItem(package_reference_id=w["package"].package_id, item_name="Paneer", quantity="400 g",
                        quantity_value=Decimal("400"), quantity_unit="g", item_order=2),
    ])
    db.commit()
    detail = _ok(client.get(f"{API}/user/menu/packages/{w['package'].package_id}", headers=w["user_auth"]))
    counts = {i["item_name"]: i["quantity_count"] for i in detail["items"]}
    assert counts["Roti"] == 4 and counts["Paneer"] is None  # never "400 g" to a customer
    _sub_id(client, w, qty=2)
    summary = _ok(client.get(f"{K}/food-summary", headers=w["kitchen_auth"]))
    by_name = {i["item_name"]: i for i in summary["items"]}
    assert by_name["Roti"]["total_servings"] == 2 and by_name["Roti"]["total_quantity"] == 8
    assert by_name["Paneer"]["total_quantity"] is None


# ══ Bug 6: preparing / ready for pickup at any time ═══════════

def test_kitchen_prepares_and_packs_a_meal_before_its_date(client, db):
    w = f.world(db)
    sub_id = _sub_id(client, w)
    meal = _meal(db, sub_id, TOMORROW)
    listed = _ok(client.get(f"{K}/subscription-orders", headers=w["kitchen_auth"], params={"order_date": "2026-10-06"}))
    view = next(o for o in listed["orders"] if o["order_id"] == str(meal.order_id))
    assert set(view["next_actions"]) >= {"preparing", "ready_for_pickup"}

    _ok(client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"], json={"status": "preparing"}))
    _ok(client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"],
                   json={"status": "ready_for_pickup"}))
    assert _meal(db, sub_id, TOMORROW).status == "ready_for_pickup"
    # never backwards
    r = client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"], json={"status": "preparing"})
    assert r.status_code == 400
    # the customer was told
    from app.models.notification_model import Notification
    assert db.query(Notification).filter(Notification.user_reference_id == w["user"].user_id,
                                         Notification.title == "Your meal is being prepared").count() >= 1


def test_batch_for_a_later_day_can_be_started_and_packed(client, db):
    w = f.world(db)
    sub_id = _sub_id(client, w)
    for target in ("preparing", "ready_for_pickup"):
        _ok(client.put(f"{K}/batch/status", headers=w["kitchen_auth"],
                       json={"order_date": "2026-10-06", "meal_slot": "lunch", "status": target}))
    assert _meal(db, sub_id, TOMORROW).status == "ready_for_pickup"
    batch = _ok(client.get(f"{K}/next-batch", headers=w["kitchen_auth"]))["batch"]
    assert batch is None or batch["can_start_preparing"] or batch["can_mark_ready"] or batch["status"] == "ready_for_pickup"


def test_one_time_order_confirmed_and_prepared_before_its_date(client, db):
    w = f.world(db, balance="1000")
    placed = _ok(client.post(f"{API}/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-08", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    }))
    oid = placed["orders"][0]["extra_order_id"]
    for status in ("confirmed", "preparing", "ready_for_pickup"):
        _ok(client.put(f"{K}/extra/{oid}/status", headers=w["kitchen_auth"], json={"status": status}))


def test_a_meal_packed_ahead_is_replanned_by_a_later_holiday(client, db):
    w = f.world(db)
    sub_id = _sub_id(client, w)
    meal = _meal(db, sub_id, TOMORROW)
    _ok(client.put(f"{K}/subscription-orders/{meal.order_id}/status", headers=w["kitchen_auth"],
                   json={"status": "ready_for_pickup"}))
    end = db.get(Subscription, uuid.UUID(sub_id)).end_date
    _ok(client.post(f"{API}/provider/holidays", headers=w["kitchen_auth"],
                    json={"rule_type": "dates", "dates": ["2026-10-06"]}))
    db.expire_all()
    moved = _meal(db, sub_id, TOMORROW)
    assert moved.status == "cancelled" and moved.cancel_reason == "vendor_holiday"
    assert db.get(Subscription, uuid.UUID(sub_id)).end_date > end  # the meal is made up at the plan end


# ══ Bug 5: every credit exact to the paisa ════════════════════

def test_wallet_credits_keep_every_paisa(client, db):
    user, _, hdr = f.customer(db, balance="0")
    for amount in ("1", "120", "0.50", "12.75"):
        r = _ok(client.post(f"{API}/user/wallet/recharge", headers=hdr, json={"amount": amount}))
        assert Decimal(str(r["amount_added"])) == Decimal(amount)
    assert _balance(db, user) == Decimal("134.25")
    txns = db.query(WalletTransaction).filter(WalletTransaction.user_reference_id == user.user_id).all()
    signed = sum((t.amount if t.type == "credit" else -t.amount for t in txns), Decimal("0"))
    assert signed == _balance(db, user)
    history = _ok(client.get(f"{API}/user/wallet/transactions", headers=hdr))["transactions"]
    assert sorted(Decimal(str(t["amount"])) for t in history) == [Decimal("0.50"), Decimal("1.00"), Decimal("12.75"),
                                                                    Decimal("120.00")]


def test_switch_credit_and_charge_are_exact_not_floored(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    cheaper = f.package(db, w["kitchen"], w["category"], price="150.25")
    b = _switch_preview(client, w, sub_id, cheaper)["price_breakup"]
    # 6 remaining meals: 6 x 180 = 1080.00 unused, new cost 6 x 150.25 = 901.50
    assert b["total"] == "-178.50" and _sum(b) == Decimal("-178.50")
    assert next(l for l in b["lines"] if l["key"] == "rounding")["amount"] == "0.00"
    before = _balance(db, w["user"])
    _ok(_switch(client, w, sub_id, cheaper, expected_total=b["total"]))
    assert _balance(db, w["user"]) - before == Decimal("178.50")


def test_switch_upgrade_charges_the_exact_difference(client, db):
    w = f.world(db, balance="5000")
    sub_id = _sub_id(client, w)
    dearer = f.package(db, w["kitchen"], w["category"], price="200.10")
    b = _switch_preview(client, w, sub_id, dearer)["price_breakup"]
    assert b["total"] == "120.60"  # 6 x 200.10 - 6 x 180
    before = _balance(db, w["user"])
    _ok(_switch(client, w, sub_id, dearer, expected_total=b["total"]))
    assert before - _balance(db, w["user"]) == Decimal("120.60")


# ══ Bug 3: price breakup on every screen ══════════════════════

def test_package_detail_shows_one_meal_breakup(client, db):
    w = f.world(db, price="180")
    _, admin = f.admin(db)
    _ok(client.put(f"{API}/admin/pricing/delivery_charge", headers=admin, json={
        "calc_type": "fixed", "charge_basis": "per_delivery", "applies_to": "all", "is_active": True,
        "value": "15.50", "change_reason": "test setup",
    }))
    b = _ok(client.get(f"{API}/user/menu/packages/{w['package'].package_id}", headers=w["user_auth"]))["price_breakup"]
    assert _sum(b) == Decimal(b["total"]) == Decimal("195.50")
    item = b["lines"][0]
    assert item["kind"] == "charge" and item["meta"]["quantity"] == 1 and item["amount"] == "180.00"
    assert {l["kind"] for l in b["lines"]} >= {"charge", "discount", "fee", "tax"}


def test_every_one_time_order_line_has_a_breakup_matching_its_total(client, db):
    w = f.world(db, balance="2000")
    _, admin = f.admin(db)
    _ok(client.put(f"{API}/admin/pricing/delivery_charge", headers=admin, json={
        "calc_type": "fixed", "charge_basis": "per_delivery", "applies_to": "all", "is_active": True,
        "value": "20", "change_reason": "test setup",
    }))
    second = f.package(db, w["kitchen"], w["category"], price="99.50")
    placed = _ok(client.post(f"{API}/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-06", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1},
                  {"package_id": str(second.package_id), "quantity": 2}],
    }))
    mine = _ok(client.get(f"{API}/user/order/extra", headers=w["user_auth"]))
    rows = mine.get("orders") or mine.get("extra_orders")
    assert len(rows) == 2
    for row in rows:
        b = row["price_breakup"]
        assert b is not None and _sum(b) == Decimal(b["total"]) == Decimal(str(row["total_price"]))
    assert sum(Decimal(str(r["total_price"])) for r in rows) == Decimal(str(placed["total_amount"]))

    admin_rows = _ok(client.get(f"{API}/admin/orders/extra-orders", headers=admin))["orders"]
    for row in admin_rows:
        assert Decimal(row["price_breakup"]["total"]) == Decimal(str(row["total_price"]))


def test_older_plans_still_show_a_breakup_that_adds_up(client, db):
    w = f.world(db)
    sub_id = _sub_id(client, w)
    sub = db.get(Subscription, uuid.UUID(sub_id))
    sub.pricing_snapshot = None  # a plan bought before breakups were kept
    db.commit()
    view = _ok(client.get(f"{S}/{sub_id}", headers=w["user_auth"]))
    b = view.get("price_breakup") or view.get("subscription", {}).get("price_breakup")
    assert b is not None and Decimal(b["total"]) == Decimal(str(sub.final_amount)) == _sum(b)
    listed = _ok(client.get(S, headers=w["user_auth"]))["subscriptions"][0]
    assert listed["price_breakup"]["total"] == b["total"]
    _, admin = f.admin(db)
    detail = _ok(client.get(f"{API}/admin/orders/subscriptions/{sub_id}", headers=admin))
    assert detail["price_breakup"]["total"] == b["total"]


# ══ Holidays still block orders ═══════════════════════════════

def test_planned_holiday_blocks_one_time_orders_and_plan_meals(client, db):
    w = f.world(db, balance="2000")
    _ok(client.post(f"{API}/provider/holidays", headers=w["kitchen_auth"], json={"rule_type": "dates", "dates": ["2026-10-07"]}))
    r = client.post(f"{API}/user/order/extra", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-07", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 400 and r.json()["code"] == "KITCHEN_HOLIDAY"
    sub_id = _sub_id(client, w)
    days = {o.order_date for o in db.query(Order).filter(Order.subscription_reference_id == sub_id,
                                                         Order.status != "cancelled")}
    assert date(2026, 10, 7) not in days and TODAY in days
