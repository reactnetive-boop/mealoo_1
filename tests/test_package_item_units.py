"""Package items carry a quantity with a unit ("400 g", "4 pcs", "1 bowl (300 g)")."""

from decimal import Decimal

import pytest

from app.domain import item_quantity
from app.models.menu_package_item_model import MenuPackageItem
from app.models.menu_package_model import MenuPackage
from tests import factories as f

MENU = "/api/v1/menu"
ITEM = "/api/v1/package/item"
ADMIN = "/api/v1/admin/packages"
CUSTOMER_MENU = "/api/v1/user/menu/packages"
FOOD_SUMMARY = "/api/v1/provider/orders/food-summary"


def _items(db, package_id):
    db.expire_all()
    pkg = db.query(MenuPackage).filter(MenuPackage.package_id == package_id).one()
    return sorted(pkg.items, key=lambda i: i.item_order or 0)


def _create(client, hdr, cat, items):
    return client.post(f"{MENU}/package", headers=hdr, json={
        "category_id": str(cat.category_id), "package_name": "Chicken Thali", "meal_type": ["lunch"],
        "food_type": "non_veg", "price": "200", "items": items,
    })


# ── Labels and rules ──────────────────────────────────────────

@pytest.mark.parametrize("fields, label", [
    ({"quantity_value": "400", "quantity_unit": "g"}, "400 g"),
    ({"quantity_value": "1.5", "quantity_unit": "kg"}, "1.5 kg"),
    ({"quantity_value": "4", "quantity_unit": "pcs"}, "4 pcs"),
    ({"quantity_value": "1", "quantity_unit": "pcs"}, "1 pc"),
    ({"quantity_value": "250", "quantity_unit": "ml"}, "250 ml"),
    ({"quantity_value": "1", "quantity_unit": "L"}, "1 L"),
    ({"quantity_value": "1", "quantity_unit": "bowl"}, "1 bowl"),
    ({"quantity_value": "1", "quantity_unit": "bowl", "bowl_capacity": "300", "bowl_capacity_unit": "g"}, "1 bowl (300 g)"),
    ({"quantity_value": "2", "quantity_unit": "bowl", "bowl_capacity": "250", "bowl_capacity_unit": "ml"}, "2 bowls (250 ml each)"),
    ({"quantity": " 2 "}, "2"),  # older app versions: free text kept as sent
])
def test_labels(fields, label):
    assert item_quantity.normalize(**fields)["quantity"] == label


@pytest.mark.parametrize("fields", [
    {"quantity_value": "400"},                                   # no unit
    {"quantity_unit": "g"},                                      # no amount
    {"quantity_value": "0", "quantity_unit": "g"},
    {"quantity_value": "400", "quantity_unit": "cups"},
    {"quantity_value": "2.5", "quantity_unit": "pcs"},           # pieces are whole
    {"quantity_value": "1.005", "quantity_unit": "kg"},
    {"quantity_value": "400", "quantity_unit": "g", "bowl_capacity": "300", "bowl_capacity_unit": "g"},
    {"quantity_value": "1", "quantity_unit": "bowl", "bowl_capacity": "300"},
    {"quantity_value": "1", "quantity_unit": "bowl", "bowl_capacity": "300", "bowl_capacity_unit": "kg"},
])
def test_invalid_quantities_are_refused(fields):
    with pytest.raises(ValueError):
        item_quantity.normalize(**fields)


def test_totals_for_the_kitchen():
    rice = item_quantity.normalize(quantity_value="400", quantity_unit="g")
    assert item_quantity.total(rice, 10) == "4 kg"
    assert item_quantity.total(rice, 2) == "800 g"
    dal = item_quantity.normalize(quantity_value="250", quantity_unit="ml")
    assert item_quantity.total(dal, 6) == "1.5 L"
    sabji = item_quantity.normalize(quantity_value="1", quantity_unit="bowl", bowl_capacity="300", bowl_capacity_unit="g")
    assert item_quantity.total(sabji, 3) == "3 bowls (300 g each)"
    assert item_quantity.total(item_quantity.normalize(quantity="2"), 5) is None


# ── Kitchen creates a package ─────────────────────────────────

def test_package_items_are_saved_with_units_and_shown_everywhere(client, db):
    w = f.world(db)
    _, admin_hdr = f.admin(db)
    r = _create(client, w["kitchen_auth"], w["category"], [
        {"item_name": "Rice", "quantity_value": 400, "quantity_unit": "g"},
        {"item_name": "Chicken", "quantity_value": 4, "quantity_unit": "pcs"},
        {"item_name": "Roti", "quantity_value": 4, "quantity_unit": "pcs"},
        {"item_name": "Sabji", "quantity_value": 1, "quantity_unit": "bowl", "bowl_capacity": 300, "bowl_capacity_unit": "g"},
        {"item_name": "Daal", "quantity_value": 250, "quantity_unit": "ml"},
    ])
    assert r.status_code == 200, r.text
    package_id = r.json()["package_id"]

    rows = _items(db, package_id)
    assert [(i.item_name, i.quantity) for i in rows] == [
        ("Rice", "400 g"), ("Chicken", "4 pcs"), ("Roti", "4 pcs"), ("Sabji", "1 bowl (300 g)"), ("Daal", "250 ml"),
    ]
    sabji = rows[3]
    assert (sabji.quantity_value, sabji.quantity_unit, sabji.bowl_capacity, sabji.bowl_capacity_unit) == (
        Decimal("1.00"), "bowl", Decimal("300.00"), "g",
    )

    # kitchen's own view
    detail = client.get(f"{MENU}/get/{package_id}", headers=w["kitchen_auth"]).json()
    assert {k: detail["items"][3][k] for k in ("quantity", "quantity_value", "quantity_unit", "bowl_capacity", "bowl_capacity_unit")} == {
        "quantity": "1 bowl (300 g)", "quantity_value": 1.0, "quantity_unit": "bowl",
        "bowl_capacity": 300.0, "bowl_capacity_unit": "g",
    }

    # customer sees the same measurements once the package is approved
    assert client.put(f"{ADMIN}/{package_id}/approve", headers=admin_hdr, json={}).status_code == 200
    seen = client.get(f"{CUSTOMER_MENU}/{package_id}", headers=w["user_auth"]).json()
    assert [(i["item_name"], i["quantity"]) for i in seen["items"]] == [
        ("Rice", "400 g"), ("Chicken", "4 pcs"), ("Roti", "4 pcs"), ("Sabji", "1 bowl (300 g)"), ("Daal", "250 ml"),
    ]
    assert seen["items"][0]["quantity_value"] == 400.0 and seen["items"][0]["quantity_unit"] == "g"


def test_bad_quantities_are_rejected_and_old_apps_still_work(client, db):
    w = f.world(db)
    hdr, cat = w["kitchen_auth"], w["category"]
    assert _create(client, hdr, cat, [{"item_name": "Rice", "quantity_value": 400}]).status_code == 422
    assert _create(client, hdr, cat, [{"item_name": "Roti", "quantity_value": 2.5, "quantity_unit": "pcs"}]).status_code == 422
    assert _create(client, hdr, cat, [
        {"item_name": "Rice", "quantity_value": 400, "quantity_unit": "g", "bowl_capacity": 300, "bowl_capacity_unit": "g"},
    ]).status_code == 422

    # an older kitchen app sends a bare count with no unit
    r = _create(client, hdr, cat, [{"item_name": "Rice", "quantity": "2"}, {"item_name": "Pickle"}])
    assert r.status_code == 200, r.text
    rows = _items(db, r.json()["package_id"])
    assert [(i.quantity, i.quantity_unit, i.quantity_value) for i in rows] == [("2", None, None), (None, None, None)]


# ── Editing items ─────────────────────────────────────────────

def test_item_quantity_can_be_changed_on_a_package_awaiting_review(client, db):
    kitchen, hdr = f.provider(db)
    pkg = f.package(db, kitchen, f.category(db), approved=False)
    item = _items(db, pkg.package_id)[0]

    r = client.put(f"{ITEM}/update/{item.item_id}", headers=hdr, json={"quantity_value": 400, "quantity_unit": "g"})
    assert r.status_code == 200, r.text
    item = _items(db, pkg.package_id)[0]
    assert (item.quantity, item.quantity_value, item.quantity_unit) == ("400 g", Decimal("400.00"), "g")

    # renaming alone keeps the quantity
    assert client.put(f"{ITEM}/update/{item.item_id}", headers=hdr, json={"item_name": "Jeera Rice"}).status_code == 200
    item = _items(db, pkg.package_id)[0]
    assert (item.item_name, item.quantity) == ("Jeera Rice", "400 g")

    # switching to bowls replaces every quantity field
    r = client.put(f"{ITEM}/update/{item.item_id}", headers=hdr, json={
        "quantity_value": 1, "quantity_unit": "bowl", "bowl_capacity": 350, "bowl_capacity_unit": "g",
    })
    assert r.status_code == 200, r.text
    item = _items(db, pkg.package_id)[0]
    assert (item.quantity, item.quantity_unit, item.bowl_capacity) == ("1 bowl (350 g)", "bowl", Decimal("350.00"))

    r = client.put(f"{ITEM}/update/{item.item_id}", headers=hdr, json={"quantity_value": 2, "quantity_unit": "litre"})
    assert r.status_code == 422


def test_item_with_unit_on_a_live_package_goes_through_review(client, db):
    w = f.world(db)
    _, admin_hdr = f.admin(db)
    pkg, hdr = w["package"], w["kitchen_auth"]

    r = client.post(f"{ITEM}/add", headers=hdr, json={
        "package_id": str(pkg.package_id), "item_name": "Dal",
        "quantity_value": 1, "quantity_unit": "bowl", "bowl_capacity": 250, "bowl_capacity_unit": "ml",
    })
    assert r.status_code == 200, r.text
    assert r.json()["has_pending_changes"] is True
    db.expire_all()
    pending = db.query(MenuPackage).filter(MenuPackage.package_id == pkg.package_id).one().pending_changes["items"]
    assert pending[-1]["quantity"] == "1 bowl (250 ml)" and pending[-1]["bowl_capacity"] == 250.0
    # the live version is still on sale unchanged
    assert [i.item_name for i in _items(db, pkg.package_id)] == ["Rice"]

    assert client.put(f"{ADMIN}/{pkg.package_id}/approve", headers=admin_hdr, json={}).status_code == 200
    dal = _items(db, pkg.package_id)[-1]
    assert (dal.item_name, dal.quantity, dal.quantity_value, dal.quantity_unit, dal.bowl_capacity, dal.bowl_capacity_unit) == (
        "Dal", "1 bowl (250 ml)", Decimal("1.00"), "bowl", Decimal("250.00"), "ml",
    )


# ── Food summary ──────────────────────────────────────────────

def test_food_summary_totals_use_the_units(client, db):
    w = f.world(db)
    item = db.query(MenuPackageItem).filter(MenuPackageItem.package_reference_id == w["package"].package_id).one()
    for field, value in item_quantity.normalize(quantity_value="400", quantity_unit="g").items():
        setattr(item, field, value)
    db.commit()

    r = client.post("/api/v1/user/subscription", headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id),
        "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id),
        "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 3}],
    })
    assert r.status_code == 200, r.text

    summary = client.get(FOOD_SUMMARY, headers=w["kitchen_auth"]).json()
    assert summary["items"] == [
        {"item_name": "Rice", "quantity_per_serving": "400 g", "total_servings": 3, "total_quantity": "1.2 kg"},
    ]
