"""
End-to-end business chain through the public APIs only (master audit section 93):

admin sets up area + plan -> kitchen registers, completes profile, is approved
-> kitchen creates a package, admin approves it -> partner registers, uploads
KYC, admin verifies and approves -> customer registers, adds address, tops up,
quotes and subscribes (today's meal is created) -> kitchen prepares and assigns
-> partner picks up with the kitchen code and delivers with the customer code
-> kitchen, partner and platform ledgers are booked once -> kitchen withdraws
and admin pays -> customer reviews -> admin dashboard reflects it all.
"""

import io
from decimal import Decimal

from tests import factories as f
from tests.test_security import _png

API = "/api/v1"


def _ok(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url}: {r.status_code} {r.text}"
    return r.json()


def test_full_platform_chain(client, db):
    _, admin = f.admin(db)

    # ── Admin: service area, plan, category ────────────────────
    _ok(client.post(f"{API}/admin/pincodes", headers=admin, json={"pincode": 560001, "city": "Bengaluru", "state": "Karnataka"}))
    plan = _ok(client.post(f"{API}/admin/plans", headers=admin, json={
        "subscription_type": "weekly", "meal_slot": "lunch", "duration_days": 7, "free_skips": 1, "discount_percent": "10",
    }))["plan"]
    cat = f.category(db)

    # ── Kitchen onboarding ─────────────────────────────────────
    otp = _ok(client.post(f"{API}/auth/generate-otp", json={"mobile_number": "9811111111", "password": "Kitchen@123"}))["otp"]
    _ok(client.post(f"{API}/auth/verify-otp", json={"mobile_number": "9811111111", "otp": otp}))
    k_token = _ok(client.post(f"{API}/auth/login", json={"mobile_number": "9811111111", "password": "Kitchen@123"}))["access_token"]
    kitchen = f.auth(k_token)
    assert _ok(client.get(f"{API}/provider/me/state", headers=kitchen))["next_step"] == "complete_profile"
    _ok(client.put(f"{API}/provider/complete-profile", headers=kitchen, json={
        "full_name": "Asha Cook", "business_name": "Asha Home Kitchen", "city": "Bengaluru", "area": "Central",
        "address": "12 MG Road", "kitchen_type": "home", "pincode": 560001, "house_no": "12", "state": "Karnataka",
        "meal_service_type": "Full Day", "daily_meal_quota": 50,
    }))
    state = _ok(client.get(f"{API}/provider/me/state", headers=kitchen))
    assert state["next_step"] == "awaiting_approval"
    assert client.post(f"{API}/menu/package", headers=kitchen, json={}).status_code == 403  # not approved yet
    _ok(client.put(f"{API}/admin/providers/{state['provider_id']}/approve", headers=admin))
    assert _ok(client.get(f"{API}/provider/me/state", headers=kitchen))["next_step"] == "dashboard"

    # ── Package: created pending, approved by admin ────────────
    pkg = _ok(client.post(f"{API}/menu/package", headers=kitchen, json={
        "category_id": str(cat.category_id), "package_name": "South Indian Thali", "meal_type": ["lunch"],
        "food_type": "veg", "price": "200", "discounted_price": "180", "is_subscription_available": True,
        "subscription_price": "170", "daily_capacity": 20, "items": [{"item_name": "Rice"}, {"item_name": "Sambar"}],
    }))
    package_id = pkg["package_id"]
    assert pkg["approval_status"] == "pending"
    _ok(client.post(f"{API}/package/image/upload", headers=kitchen, params={"package_id": package_id},
                    files={"file": ("thali.png", io.BytesIO(_png()), "image/png")}))
    _ok(client.put(f"{API}/admin/packages/{package_id}/approve", headers=admin))

    # ── Delivery partner onboarding ────────────────────────────
    otp = _ok(client.post(f"{API}/delivery/auth/register", json={"mobile_number": "9822222222", "password": "Rider@1234"}))["otp"]
    d_token = _ok(client.post(f"{API}/delivery/auth/verify-otp", json={"mobile_number": "9822222222", "otp": otp}))["access_token"]
    rider = f.auth(d_token)
    _ok(client.put(f"{API}/delivery/profile", headers=rider, json={
        "full_name": "Kiran Rider", "email": "kiran@example.com", "date_of_birth": "1995-01-01", "gender": "male",
        "vehicle_type": "bike", "vehicle_number": "ka01ab1234",
    }))
    for t in ("aadhaar", "pan", "driving_license", "vehicle_rc"):
        _ok(client.post(f"{API}/delivery/documents", headers=rider, data={"document_type": t},
                        files={"file": (f"{t}.png", io.BytesIO(_png()), "image/png")}))
    _ok(client.put(f"{API}/delivery/payout-details", headers=rider, json={"upi_id": "kiran@okbank"}))
    rstate = _ok(client.get(f"{API}/delivery/me/state", headers=rider))
    assert rstate["next_step"] == "awaiting_approval"
    rider_id = rstate["delivery_boy_id"]
    detail = _ok(client.get(f"{API}/admin/delivery-boys/{rider_id}", headers=admin))
    for doc in detail["documents"]:
        file = client.get(f"{API}/admin/delivery-boys/{rider_id}/documents/{doc['delivery_boy_document_id']}/file", headers=admin)
        assert file.status_code == 200 and file.content.startswith(b"\x89PNG")
        _ok(client.put(f"{API}/admin/delivery-boys/{rider_id}/documents/{doc['delivery_boy_document_id']}/review",
                       headers=admin, json={"status": "verified"}))
    _ok(client.put(f"{API}/admin/delivery-boys/{rider_id}/approve", headers=admin))
    _ok(client.put(f"{API}/delivery/profile", headers=rider, json={"is_online": True}))

    # ── Customer ───────────────────────────────────────────────
    otp = _ok(client.post(f"{API}/user/auth/generate-otp", json={"phone": "9833333333", "password": "Customer@1"}))["otp"]
    _ok(client.post(f"{API}/user/auth/verify-otp", json={"phone": "9833333333", "otp": otp}))
    c_token = _ok(client.post(f"{API}/user/auth/login", json={"phone": "9833333333", "password": "Customer@1"}))["access_token"]
    cust = f.auth(c_token)
    assert _ok(client.get(f"{API}/user/me/state", headers=cust))["next_step"] == "add_address"
    addr = _ok(client.post(f"{API}/user/address", headers=cust, json={
        "label": "Home", "address_line1": "1 Residency Road", "city": "Bengaluru", "state": "Karnataka",
        "pin_code": "560001", "is_default": True,
    }))
    address_id = addr["address_id"]
    assert _ok(client.get(f"{API}/user/me/state", headers=cust))["next_step"] == "browse"
    listed = _ok(client.get(f"{API}/user/menu/packages", headers=cust, params={"pin_code": "560001"}))
    assert package_id in str(listed)

    _ok(client.post(f"{API}/user/wallet/recharge", headers={**cust, "Idempotency-Key": "topup-1"}, json={"amount": "2000"}))
    _ok(client.post(f"{API}/user/wallet/recharge", headers={**cust, "Idempotency-Key": "topup-1"}, json={"amount": "2000"}))

    kitchen_id = state["provider_id"]
    quote = _ok(client.post(f"{API}/user/subscription/quote", headers=cust, json={
        "vendor_id": kitchen_id, "package_id": package_id, "plan_id": plan["subscription_plan_id"],
        "address_id": address_id, "start_date": "2026-10-05",
    }))
    # 7 x 170 = 1190, 10% plan discount = 119 -> 1071
    assert Decimal(quote["total_payable"]) == Decimal("1071.00")
    sub = _ok(client.post(f"{API}/user/subscription", headers={**cust, "Idempotency-Key": "sub-1"}, json={
        "vendor_id": kitchen_id, "plan_id": plan["subscription_plan_id"], "address_id": address_id,
        "start_date": "2026-10-05", "items": [{"package_id": package_id, "quantity": 1}],
    }))
    assert Decimal(sub["final_amount"]) == Decimal("1071.00")
    wallet = _ok(client.get(f"{API}/user/wallet", headers=cust))["wallet"]
    assert Decimal(str(wallet["balance"])) == Decimal("929.00")  # one top-up only

    meals = _ok(client.get(f"{API}/user/subscription/{sub['subscription_id']}/orders", headers=cust))["orders"]
    today = [m for m in meals if m["order_date"] == "2026-10-05"][0]
    customer_code = today["otp_for_delivery"]
    assert customer_code

    # ── Kitchen prepares and assigns ───────────────────────────
    k_orders = _ok(client.get(f"{API}/provider/orders/subscription-orders", headers=kitchen, params={"order_date": "2026-10-05"}))["orders"]
    k_meal = [o for o in k_orders if str(o["order_id"]) == str(today["order_id"])][0]
    assert "otp_for_delivery" not in k_meal
    pickup_code = k_meal["pickup_code"]
    _ok(client.put(f"{API}/provider/orders/subscription-orders/{today['order_id']}/status", headers=kitchen, json={"status": "preparing"}))
    partners = _ok(client.get(f"{API}/provider/delivery-partners", headers=kitchen))["delivery_partners"]
    assert rider_id in str(partners)
    _ok(client.put(f"{API}/provider/orders/subscription-orders/{today['order_id']}/assign-delivery-boy", headers=kitchen,
                   json={"delivery_boy_id": rider_id}))

    # ── Partner hand-over ──────────────────────────────────────
    assigned = _ok(client.get(f"{API}/delivery/orders", headers=rider))["orders"]
    assert len(assigned) == 1
    _ok(client.put(f"{API}/delivery/orders/{today['order_id']}/pickup", headers=rider, json={"pickup_code": pickup_code}))
    _ok(client.put(f"{API}/delivery/orders/{today['order_id']}/deliver", headers=rider, json={"otp": customer_code}))

    # ── Money ──────────────────────────────────────────────────
    k_wallet = _ok(client.get(f"{API}/provider/wallet", headers=kitchen))["wallet"]
    assert Decimal(str(k_wallet["balance"])) == Decimal("170.00")  # full base price; the plan discount is Orleeno's
    r_wallet = _ok(client.get(f"{API}/delivery/wallet", headers=rider))["wallet"]
    assert Decimal(str(r_wallet["balance"])) == Decimal("30.00")
    earnings = _ok(client.get(f"{API}/delivery/earnings", headers=rider))
    assert earnings["today"]["deliveries"] == 1

    _ok(client.post(f"{API}/provider/wallet/withdraw", headers=kitchen, json={"amount": "100"}))
    req = _ok(client.get(f"{API}/admin/payouts", headers=admin, params={"status": "pending"}))["requests"][0]
    _ok(client.put(f"{API}/admin/payouts/{req['payout_request_id']}", headers=admin,
                   json={"action": "paid", "payout_reference": "UTR0001"}))
    _ok(client.post(f"{API}/delivery/wallet/withdraw", headers=rider, json={"amount": "30"}))

    # ── Review (only after a real delivery) ────────────────────
    _ok(client.post(f"{API}/user/review", headers=cust, json={
        "vendor_id": kitchen_id, "vendor_rating": 5, "review_text": "Lovely food",
        "subscription_id": sub["subscription_id"],
    }))

    # ── Admin overview ─────────────────────────────────────────
    dash = _ok(client.get(f"{API}/admin/dashboard", headers=admin))
    assert dash["orders"]["today_delivered"] == 1
    assert dash["subscriptions"]["active"] == 1
    assert dash["revenue"]["pending_withdrawals"] == 1  # the partner's request
