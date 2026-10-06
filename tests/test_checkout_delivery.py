"""BE-B1: a one-time checkout with several packages is ONE delivery."""

from decimal import Decimal

from app.domain import verification
from app.models.delivery_boy_wallet_model import DeliveryBoyWallet
from app.models.extra_order_model import ExtraOrder
from app.models.provider_wallet_model import ProviderWallet
from app.models.wallet_model import Wallet
from tests import factories as f

E = "/api/v1/user/order/extra"
K = "/api/v1/provider/orders"
D = "/api/v1/delivery"


def _two_package_checkout(client, db, *, delivery_charge="20"):
    _, admin_hdr = f.admin(db)
    r = client.put("/api/v1/admin/pricing/delivery_charge", headers=admin_hdr, json={
        "calc_type": "fixed", "value": delivery_charge, "charge_basis": "per_delivery", "change_reason": "checkout test fee",
    })
    assert r.status_code == 200, r.text
    w = f.world(db, price="100", balance="1000")
    second = f.package(db, w["kitchen"], w["category"], price="150")
    body = {
        "vendor_id": str(w["kitchen"].provider_id), "address_id": str(w["address"].user_address_id),
        "delivery_date": "2026-10-05", "meal_slot": "lunch",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1},
                  {"package_id": str(second.package_id), "quantity": 1}],
    }
    r = client.post(E, headers=w["user_auth"], json=body)
    assert r.status_code == 200, r.text
    db.expire_all()
    lines = db.query(ExtraOrder).order_by(ExtraOrder.extra_order_id).all()
    assert len(lines) == 2 and lines[0].checkout_id == lines[1].checkout_id
    return w, lines, r.json()


def test_trip_charges_and_partner_payout_are_counted_once(client, db):
    w, lines, placed = _two_package_checkout(client, db)
    # 100 + 150 food + one delivery charge of 20, not two
    assert Decimal(placed["total_amount"]) == Decimal("270.00")
    payouts = sorted(Decimal(o.pricing_snapshot["settlement"]["partner_payout_total"]) for o in lines)
    assert payouts == [Decimal("0.00"), Decimal("30.00")]


def test_lines_share_one_delivery_code(client, db):
    _, lines, _ = _two_package_checkout(client, db)
    assert verification.delivery_code(lines[0]) == verification.delivery_code(lines[1])
    # a lone one-time order elsewhere has a different code
    other = ExtraOrder(checkout_id=None, extra_order_id=lines[0].extra_order_id,
                       delivery_code_seed=lines[0].delivery_code_seed.removeprefix("c:"))
    assert verification.delivery_code(other) != verification.delivery_code(lines[0])


def test_one_trip_assign_pickup_deliver_and_pay_once(client, db):
    w, lines, _ = _two_package_checkout(client, db)
    kitchen_hdr = w["kitchen_auth"]
    for line in lines:
        for status in ("confirmed", "preparing", "ready_for_pickup"):
            r = client.put(f"{K}/extra/{line.extra_order_id}/status", headers=kitchen_hdr, json={"status": status})
            assert r.status_code == 200, r.text

    boy, boy_hdr = f.delivery_boy(db, kitchen=w["kitchen"])
    r = client.put(f"{K}/extra/{lines[0].extra_order_id}/assign-delivery-boy", headers=kitchen_hdr,
                   json={"delivery_boy_id": str(boy.delivery_boy_id)})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert {o.delivery_boy_reference_id for o in db.query(ExtraOrder).all()} == {boy.delivery_boy_id}

    first = str(lines[0].extra_order_id)
    r = client.put(f"{D}/extra-orders/{first}/pickup", headers=boy_hdr,
                   json={"pickup_code": f.pickup_code(db, w["kitchen"])})
    assert r.status_code == 200, r.text
    assert r.json()["also_updated"] == [str(lines[1].extra_order_id)]

    assert client.put(f"{D}/extra-orders/{first}/start-delivery", headers=boy_hdr).status_code == 200
    db.expire_all()
    code = verification.delivery_code(db.get(ExtraOrder, lines[1].extra_order_id))
    r = client.put(f"{D}/extra-orders/{first}/deliver", headers=boy_hdr, json={"otp": code})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert {o.status for o in db.query(ExtraOrder).all()} == {"delivered"}
    partner = db.query(DeliveryBoyWallet).filter(DeliveryBoyWallet.delivery_boy_reference_id == boy.delivery_boy_id).one()
    assert partner.balance == Decimal("30.00")  # one trip, paid once
    kitchen = db.query(ProviderWallet).filter(ProviderWallet.provider_reference_id == w["kitchen"].provider_id).one()
    assert kitchen.balance == Decimal("250.00")  # both packages


def test_customer_cancel_cancels_the_whole_checkout(client, db):
    w, lines, placed = _two_package_checkout(client, db)
    r = client.put(f"{E}/{lines[1].extra_order_id}/cancel", headers=w["user_auth"])
    assert r.status_code == 200, r.text
    db.expire_all()
    assert {o.status for o in db.query(ExtraOrder).all()} == {"cancelled"}
    assert db.query(Wallet).filter(Wallet.user_reference_id == w["user"].user_id).one().balance == Decimal("1000.00")


def test_cancel_refused_once_the_kitchen_accepted_part(client, db):
    w, lines, _ = _two_package_checkout(client, db)
    client.put(f"{K}/extra/{lines[0].extra_order_id}/status", headers=w["kitchen_auth"], json={"status": "confirmed"})
    r = client.put(f"{E}/{lines[1].extra_order_id}/cancel", headers=w["user_auth"])
    assert r.status_code == 400
