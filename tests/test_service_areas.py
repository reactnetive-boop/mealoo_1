"""PR-02: a kitchen can deliver to more pincodes than its own."""

from tests import factories as f

S = "/api/v1/user/subscription"
MENU = "/api/v1/user/menu/packages"


def _setup(client, db):
    w = f.world(db)                           # kitchen in 560001
    f.pincode(db, 560002)
    user, address, user_hdr = f.customer(db, balance="5000", pin=560002)
    _, admin_hdr = f.admin(db)
    base = f"/api/v1/admin/providers/{w['kitchen'].provider_id}/service-areas"
    return w, address, user_hdr, admin_hdr, base


def _menu(client, hdr):
    return client.get(MENU, headers=hdr, params={"pin_code": 560002}).json()["packages"]


def test_service_area_opens_a_neighbouring_pincode(client, db):
    w, address, user_hdr, admin_hdr, base = _setup(client, db)
    assert _menu(client, user_hdr) == []

    r = client.post(base, headers=admin_hdr, json={"pincode": 560002})
    assert r.status_code == 200, r.text
    assert r.json()["all_pincodes"] == [560001, 560002]
    assert [p["package_id"] for p in _menu(client, user_hdr)] == [str(w["package"].package_id)]

    r = client.post(S, headers=user_hdr, json={
        "vendor_id": str(w["kitchen"].provider_id), "plan_id": str(w["plan"].subscription_plan_id),
        "address_id": str(address.user_address_id), "start_date": "2026-10-05",
        "items": [{"package_id": str(w["package"].package_id), "quantity": 1}],
    })
    assert r.status_code == 200, r.text

    # cannot pull the area out from under a running subscription
    r = client.delete(f"{base}/560002", headers=admin_hdr)
    assert r.status_code == 409 and r.json()["code"] == "AREA_IN_USE"
    kitchen_view = client.get("/api/v1/provider/service-areas", headers=w["kitchen_auth"]).json()
    assert kitchen_view["all_pincodes"] == [560001, 560002]


def test_area_rules(client, db):
    w, _, user_hdr, admin_hdr, base = _setup(client, db)
    assert client.post(base, headers=admin_hdr, json={"pincode": 560001}).status_code == 400   # own pincode
    assert client.post(base, headers=admin_hdr, json={"pincode": 560099}).status_code == 400   # not served by Orleeno
    assert client.post(base, headers=admin_hdr, json={"pincode": 560002}).status_code == 200
    assert client.post(base, headers=admin_hdr, json={"pincode": 560002}).status_code == 409   # duplicate
    assert client.delete(f"{base}/560002", headers=admin_hdr).status_code == 200
    assert _menu(client, user_hdr) == []
    assert client.delete(f"{base}/560002", headers=admin_hdr).status_code == 404
