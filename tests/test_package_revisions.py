"""BE-B3: editing a live package keeps it on sale until the edit is reviewed."""

from decimal import Decimal

from app.models.menu_package_model import MenuPackage
from app.models.provider_notification_model import ProviderNotification
from tests import factories as f

MENU = "/api/v1/menu"
ITEM = "/api/v1/package/item"
ADMIN = "/api/v1/admin/packages"
CUSTOMER_MENU = "/api/v1/user/menu/packages"


def _live(db):
    w = f.world(db, price="180")
    _, admin_hdr = f.admin(db)
    return w, w["package"], w["kitchen_auth"], admin_hdr


def _row(db, pkg):
    db.expire_all()
    return db.query(MenuPackage).filter(MenuPackage.package_id == pkg.package_id).one()


def _customer_price(client, w, pkg):
    listing = client.get(CUSTOMER_MENU, headers=w["user_auth"], params={"pin_code": f.PIN}).json()["packages"]
    return next(Decimal(str(p["price"])) for p in listing if p["package_id"] == str(pkg.package_id))


def test_edit_waits_for_review_and_live_version_stays_on_sale(client, db):
    w, pkg, hdr, admin_hdr = _live(db)
    r = client.put(f"{MENU}/update/{pkg.package_id}", headers=hdr, json={"price": "200", "description": "Now with dessert"})
    assert r.status_code == 200, r.text
    assert r.json()["has_pending_changes"] is True

    row = _row(db, pkg)
    assert row.approval_status == "approved" and row.price == Decimal("180.00")
    assert _customer_price(client, w, pkg) == Decimal("180.00")

    queue = client.get(ADMIN, headers=admin_hdr, params={"has_pending_changes": True}).json()["packages"]
    assert [p["package_id"] for p in queue] == [str(pkg.package_id)]

    r = client.put(f"{ADMIN}/{pkg.package_id}/approve", headers=admin_hdr, json={})
    assert r.status_code == 200, r.text
    row = _row(db, pkg)
    assert row.price == Decimal("200.00") and row.description == "Now with dessert" and row.pending_changes is None
    assert _customer_price(client, w, pkg) == Decimal("200.00")
    assert db.query(ProviderNotification).filter(ProviderNotification.type == "package_update").count() == 1


def test_rejected_edit_is_discarded(client, db):
    w, pkg, hdr, admin_hdr = _live(db)
    client.put(f"{MENU}/update/{pkg.package_id}", headers=hdr, json={"price": "999"})
    assert client.put(f"{ADMIN}/{pkg.package_id}/reject", headers=admin_hdr, json={}).status_code in (400, 422)
    r = client.put(f"{ADMIN}/{pkg.package_id}/reject", headers=admin_hdr, json={"note": "Price too high"})
    assert r.status_code == 200, r.text
    row = _row(db, pkg)
    assert row.approval_status == "approved" and row.price == Decimal("180.00") and row.pending_changes is None


def test_reverting_an_edit_clears_the_revision(client, db):
    w, pkg, hdr, _ = _live(db)
    client.put(f"{MENU}/update/{pkg.package_id}", headers=hdr, json={"price": "200"})
    r = client.put(f"{MENU}/update/{pkg.package_id}", headers=hdr, json={"price": "180"})
    assert r.json()["has_pending_changes"] is False
    assert _row(db, pkg).pending_changes is None


def test_availability_toggle_applies_at_once(client, db):
    w, pkg, hdr, _ = _live(db)
    client.put(f"{MENU}/update/{pkg.package_id}", headers=hdr, json={"is_available": False})
    row = _row(db, pkg)
    assert row.is_available is False and row.pending_changes is None


def test_item_changes_on_a_live_package_are_a_revision(client, db):
    w, pkg, hdr, admin_hdr = _live(db)
    live_item = _row(db, pkg).items[0]

    added = client.post(f"{ITEM}/add", headers=hdr, json={"package_id": str(pkg.package_id), "item_name": "Dal", "quantity": "1 bowl"})
    assert added.status_code == 200, added.text
    new_id = added.json()["item_id"]
    assert client.put(f"{ITEM}/update/{new_id}", headers=hdr, json={"quantity": "2 bowls"}).status_code == 200
    assert client.delete(f"{ITEM}/delete/{live_item.item_id}", headers=hdr).status_code == 200

    row = _row(db, pkg)
    assert [i.item_name for i in row.items] == ["Rice"]  # still on sale as approved
    assert [(i["item_name"], i["quantity"]) for i in row.pending_changes["items"]] == [("Dal", "2 bowls")]
    # the last item cannot go
    assert client.delete(f"{ITEM}/delete/{new_id}", headers=hdr).status_code == 400

    assert client.put(f"{ADMIN}/{pkg.package_id}/approve", headers=admin_hdr, json={}).status_code == 200
    row = _row(db, pkg)
    assert [(i.item_name, i.quantity) for i in row.items] == [("Dal", "2 bowls")]


def test_package_not_yet_live_is_edited_directly(client, db):
    kitchen, hdr = f.provider(db)
    pkg = f.package(db, kitchen, f.category(db), approved=False)
    r = client.put(f"{MENU}/update/{pkg.package_id}", headers=hdr, json={"price": "150", "subscription_price": "150"})
    assert r.status_code == 200, r.text
    row = _row(db, pkg)
    assert row.price == Decimal("150.00") and row.pending_changes is None and row.approval_status == "pending"
