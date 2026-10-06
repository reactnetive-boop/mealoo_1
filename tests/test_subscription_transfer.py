"""BE-B8: moving a closing kitchen's subscriptions to another kitchen."""

from decimal import Decimal

from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.models.wallet_model import Wallet
from tests import factories as f

S = "/api/v1/user/subscription"


def _subscribe(client, w, pkg):
    r = client.post(S, headers=w["user_auth"], json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(w["address"].user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(pkg.package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text
    return r.json()["subscription_id"]


def _setup(client, db):
    w = f.world(db, balance="5000")
    catalogue = f.package(db, None, w["category"], price="150", predefined=True)
    f.offer(db, w["kitchen"], catalogue)
    target, _ = f.provider(db)
    f.offer(db, target, catalogue)
    movable = _subscribe(client, w, catalogue)
    own = _subscribe(client, w, w["package"])  # the closing kitchen's own package: cannot move
    _, admin_hdr = f.admin(db)
    url = f"/api/v1/admin/providers/{w['kitchen'].provider_id}/transfer-subscriptions"
    return w, target, movable, own, admin_hdr, url


def test_preview_lists_what_can_move(client, db):
    w, target, movable, own, admin_hdr, url = _setup(client, db)
    r = client.post(url, headers=admin_hdr, json={"target_provider_id": str(target.provider_id), "reason": "Kitchen closing"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview"] is True and body["movable"] == [movable]
    assert body["blocked"][0]["subscription_id"] == own and "does not sell" in body["blocked"][0]["reason"]
    db.expire_all()
    assert db.query(Subscription).filter(Subscription.vendor_reference_id == target.provider_id).count() == 0


def test_transfer_moves_meals_and_cancels_the_rest(client, db):
    w, target, movable, own, admin_hdr, url = _setup(client, db)
    before = db.query(Wallet).filter(Wallet.user_reference_id == w["user"].user_id).one().balance
    r = client.post(url, headers=admin_hdr, json={
        "target_provider_id": str(target.provider_id), "reason": "Kitchen closing",
        "preview": False, "cancel_untransferable": True,
    })
    assert r.status_code == 200, r.text
    db.expire_all()
    moved = db.query(Subscription).filter(Subscription.subscription_id == movable).one()
    assert moved.vendor_reference_id == target.provider_id and moved.status == "active"
    open_meals = db.query(Order).filter(Order.subscription_reference_id == movable, Order.status == "scheduled").all()
    assert open_meals and all(m.vendor_reference_id == target.provider_id for m in open_meals)
    assert db.query(Subscription).filter(Subscription.subscription_id == own).one().status == "cancelled"
    after = db.query(Wallet).filter(Wallet.user_reference_id == w["user"].user_id).one().balance
    assert after > before  # the cancelled plan's unused meals were refunded
    assert Decimal(str(r.json()["cancelled"][0]["refund_amount"])) == after - before
