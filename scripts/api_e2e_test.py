"""
End-to-end API test for the whole Mealoo platform (provider, user, delivery boy, admin).

Runs against a live server (default http://localhost:8000) and creates its own
test entities with unique phone numbers per run, so it can be re-run any time:

    python scripts/api_e2e_test.py

Covers every route registered in app/api/v1/api.py: happy paths in realistic
business order (onboarding -> catalog -> orders -> delivery -> settlement) plus
the key negative cases (bad OTP, wrong password, foreign resources, invalid
transitions, insufficient balance, policy rules).

Notes:
- OTPs are read from API responses (dev mode returns them).
- Subscription daily orders and provider billing are produced by schedulers in
  production; the test invokes those scheduler functions in-process.
- Requires the backend virtualenv (uses app.* imports for scheduler + OTP lookup).
"""

import sys
import time
import json as jsonlib
from datetime import date, timedelta
from pathlib import Path

import httpx as requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://localhost:8000"
API = f"{BASE}/api/v1"

RUN = str(int(time.time()))[-8:]          # unique per run
P1_MOBILE = "70" + RUN                     # provider 1
P2_MOBILE = "71" + RUN                     # provider 2 (for package switch)
U1_PHONE = "80" + RUN                      # customer
D1_MOBILE = "90" + RUN                     # delivery boy
PASSWORD = "E2eTest@123"
ADMIN_EMAIL = "e2e.admin@mealoo.test"
ADMIN_PASSWORD = "E2eAdmin@123"
TEST_PIN = "5" + RUN[-5:]                  # unique serviceable pincode
TODAY = date.today()

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
       b"\x00\x00\x00\x03\x00\x01\x87\xa2\x0b\xe0\x00\x00\x00\x00IEND\xaeB`\x82")

results = []
covered = set()


def call(name, method, template, *, token=None, path=None, params=None,
         json=None, files=None, data=None, expect=200, check=None):
    """Fire one request, record PASS/FAIL, return the parsed body (or None)."""
    url = API + (template.format(**path) if path else template)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.request(method, url, headers=headers, params=params,
                                json=json, files=files, data=data, timeout=60)
    except Exception as e:
        results.append(("FAIL", name, method, template, "EXC", expect, str(e)))
        return None

    covered.add((method.upper(), "/api/v1" + template))
    expected = expect if isinstance(expect, tuple) else (expect,)
    try:
        body = resp.json()
    except Exception:
        body = None

    if resp.status_code not in expected:
        detail = jsonlib.dumps(body)[:300] if body is not None else resp.text[:300]
        results.append(("FAIL", name, method, template, resp.status_code, expect, detail))
        return body

    if check:
        err = check(body)
        if err:
            results.append(("FAIL", name, method, template, resp.status_code, expect, err))
            return body

    results.append(("PASS", name, method, template, resp.status_code, expect, ""))
    return body


def section(title):
    print(f"\n{'=' * 10} {title} {'=' * 10}")


def ok(body):
    return None if (body and body.get("success") is True) else f"success!=true: {jsonlib.dumps(body)[:200]}"


def run_order_scheduler():
    from app.schedulers.order_generator import generate_subscription_orders
    generate_subscription_orders()


def get_order_otp(order_id):
    from app.core.database import SessionLocal
    from app.models.order_model import Order
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.order_id == order_id).first()
        return order.otp_for_delivery if order else None
    finally:
        db.close()


def run_billing_scheduler():
    """Skip-refund scheduler — runs per meal slot in production."""
    from app.schedulers.order_billing import process_order_billing
    for slot in ("breakfast", "lunch", "dinner"):
        process_order_billing(slot)
    return True


# ════════════════════════════════════════════════════════════
# ADMIN — auth + platform setup other roles depend on
# ════════════════════════════════════════════════════════════
section("ADMIN: auth & platform setup")

call("admin login wrong password", "POST", "/admin/auth/login",
     json={"email": ADMIN_EMAIL, "password": "wrong"}, expect=(400, 401))
body = call("admin login", "POST", "/admin/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, check=ok)
ADMIN = body["access_token"] if body else None

call("admin profile", "GET", "/admin/auth/profile", token=ADMIN)
call("admin change password (same)", "PUT", "/admin/auth/change-password", token=ADMIN,
     json={"current_password": ADMIN_PASSWORD, "new_password": ADMIN_PASSWORD})
call("admin dashboard", "GET", "/admin/dashboard", token=ADMIN)
call("admin endpoint without token", "GET", "/admin/dashboard", expect=(401, 403))

body = call("admin create pincode", "POST", "/admin/pincodes", token=ADMIN,
            json={"pincode": TEST_PIN, "city": "Testville", "state": "TestState"})
PINCODE_ID = (body or {}).get("pincode_id") or (body or {}).get("data", {}).get("pincode_id")
call("admin create duplicate pincode", "POST", "/admin/pincodes", token=ADMIN,
     json={"pincode": TEST_PIN, "city": "Testville", "state": "TestState"}, expect=(400, 409))
body = call("admin list pincodes", "GET", "/api-pincodes-alias" if False else "/admin/pincodes",
            token=ADMIN, params={"city": "Testville"})
if not PINCODE_ID and body:
    for p in body.get("pincodes", body.get("data", [])) or []:
        if str(p.get("pincode")) == TEST_PIN:
            PINCODE_ID = p.get("pincode_id")
if PINCODE_ID:
    call("admin update pincode", "PUT", "/admin/pincodes/{pid}", token=ADMIN,
         path={"pid": PINCODE_ID}, json={"city": "Testville", "state": "TestState", "is_active": True})

body = call("admin create plan", "POST", "/admin/plans", token=ADMIN,
            json={"subscription_type": "weekly", "meal_slot": "lunch",
                  "duration_days": 7, "free_skips": 1, "discount_percent": 5},
            expect=(200, 409))  # 409 when a previous run already created it
PLAN_ID = (body or {}).get("plan_id") or (body or {}).get("subscription_plan_id")
if not PLAN_ID and body:
    PLAN_ID = (body.get("plan") or {}).get("subscription_plan_id") or (body.get("plan") or {}).get("plan_id")
body = call("admin list plans", "GET", "/admin/plans", token=ADMIN)
if not PLAN_ID and body:
    for pl in body.get("plans", []) or []:
        if pl.get("subscription_type") == "weekly" and pl.get("meal_slot") == "lunch":
            PLAN_ID = pl.get("subscription_plan_id") or pl.get("plan_id")
if PLAN_ID:
    call("admin plan detail", "GET", "/admin/plans/{pid}", token=ADMIN, path={"pid": PLAN_ID})
    call("admin update plan", "PUT", "/admin/plans/{pid}", token=ADMIN,
         path={"pid": PLAN_ID}, json={"free_skips": 2})

# ════════════════════════════════════════════════════════════
# PROVIDER 1 — onboarding, catalog
# ════════════════════════════════════════════════════════════
section("PROVIDER 1: onboarding & catalog")

body = call("provider generate otp", "POST", "/auth/generate-otp",
            json={"mobile_number": P1_MOBILE, "password": PASSWORD}, check=ok)
P1_OTP = (body or {}).get("otp")
call("provider verify wrong otp", "POST", "/auth/verify-otp",
     json={"mobile_number": P1_MOBILE, "otp": "000000"}, expect=400)
call("provider verify otp", "POST", "/auth/verify-otp",
     json={"mobile_number": P1_MOBILE, "otp": P1_OTP}, check=ok)
call("provider login wrong password", "POST", "/auth/login",
     json={"mobile_number": P1_MOBILE, "password": "WrongPass@123"}, expect=(400, 401))
body = call("provider login", "POST", "/auth/login",
            json={"mobile_number": P1_MOBILE, "password": PASSWORD}, check=ok)
P1 = body.get("access_token") if body else None
P1_ID = body.get("provider_id") if body else None

call("provider profile (incomplete)", "GET", "/provider/profile", token=P1)
call("verify serviceable pincode", "POST", "/location/verify-pincode",
     json={"pincode": int(TEST_PIN)})
call("verify non-serviceable pincode", "POST", "/location/verify-pincode",
     json={"pincode": 999999}, expect=(200, 400, 404))

call("provider complete profile", "PUT", "/provider/complete-profile", token=P1,
     json={"full_name": "E2E Provider One", "business_name": "E2E Kitchen One",
           "city": "Testville", "area": "Sector 1", "address": "12 Test Street",
           "kitchen_type": "veg", "pincode": int(TEST_PIN), "house_no": "12",
           "landmark": "Near Test Park", "state": "TestState"})
call("provider address update", "PUT", "/provider/address", token=P1,
     json={"provider_id": P1_ID, "house_no": "12A", "address": "12A Test Street",
           "landmark": "Near Test Park", "city": "Testville", "state": "TestState",
           "pincode": int(TEST_PIN)})
with open(__file__, "rb"):
    pass
call("provider profile image upload", "PUT", "/provider/profile/image", token=P1,
     files={"file": ("profile.png", PNG, "image/png")})

body = call("menu categories", "GET", "/menu/categories", token=P1)
cats = (body or {}).get("categories") or (body or {}).get("data") or []
CATEGORY_ID = cats[0].get("category_id") if cats else None
if CATEGORY_ID:
    call("menu category detail", "GET", "/menu/categories/{cid}", token=P1, path={"cid": CATEGORY_ID})

body = call("provider create package", "POST", "/menu/package", token=P1,
            json={"category_id": CATEGORY_ID, "package_name": f"E2E Lunch Thali {RUN}",
                  "short_description": "Test thali", "description": "E2E test package",
                  "meal_type": "lunch", "food_type": "veg", "price": 100,
                  "is_subscription_available": True, "subscription_price": 100,
                  "items": [{"item_name": "Roti", "quantity": "4"},
                            {"item_name": "Dal", "quantity": "1 bowl"}]})
PKG1 = None
if body:
    PKG1 = body.get("package_id") or (body.get("package") or {}).get("package_id")
call("menu get package", "GET", "/menu/get/{pid}", token=P1, path={"pid": PKG1})
call("menu list by provider", "GET", "/menu/list/{prov}", token=P1, path={"prov": P1_ID})
call("menu update package", "PUT", "/menu/update/{pid}", token=P1, path={"pid": PKG1},
     json={"short_description": "Updated test thali"})

body = call("package item add", "POST", "/package/item/add", token=P1,
            json={"package_id": PKG1, "item_name": "Rice", "quantity": "1 bowl", "item_order": 3})
ITEM_ID = (body or {}).get("item_id") or ((body or {}).get("item") or {}).get("item_id")
if ITEM_ID:
    call("package item update", "PUT", "/package/item/update/{iid}", token=P1,
         path={"iid": ITEM_ID}, json={"quantity": "2 bowls"})
    call("package item delete", "DELETE", "/package/item/delete/{iid}", token=P1,
         path={"iid": ITEM_ID})

body = call("package image upload", "POST", "/package/image/upload", token=P1,
            params={"package_id": PKG1}, files={"file": ("pkg.png", PNG, "image/png")})
IMG_ID = (body or {}).get("image_id") or ((body or {}).get("image") or {}).get("image_id")
if IMG_ID:
    call("package image set primary", "PUT", "/package/image/set-primary/{iid}", token=P1,
         path={"iid": IMG_ID})
    call("package image delete", "DELETE", "/package/image/delete/{iid}", token=P1,
         path={"iid": IMG_ID})

# own packages are auto-selected at creation, so re-selecting is a 400;
# the true happy path (selecting an admin predefined package) runs in the admin section
call("provider re-select own package rejected", "POST", "/provider-package/select", token=P1,
     json={"provider_id": P1_ID, "package_id": PKG1, "daily_capacity": 50}, expect=400)
call("provider set capacity", "PUT", "/provider-package/capacity", token=P1,
     json={"provider_id": P1_ID, "package_id": PKG1, "daily_capacity": 60})

# ════════════════════════════════════════════════════════════
# PROVIDER 2 — minimal setup (target of the package switch)
# ════════════════════════════════════════════════════════════
section("PROVIDER 2: minimal setup")

body = call("provider2 generate otp", "POST", "/auth/generate-otp",
            json={"mobile_number": P2_MOBILE, "password": PASSWORD})
call("provider2 verify otp", "POST", "/auth/verify-otp",
     json={"mobile_number": P2_MOBILE, "otp": (body or {}).get("otp")})
body = call("provider2 login", "POST", "/auth/login",
            json={"mobile_number": P2_MOBILE, "password": PASSWORD})
P2 = body.get("access_token") if body else None
P2_ID = body.get("provider_id") if body else None
call("provider2 complete profile", "PUT", "/provider/complete-profile", token=P2,
     json={"full_name": "E2E Provider Two", "business_name": "E2E Kitchen Two",
           "city": "Testville", "area": "Sector 2", "address": "34 Test Street",
           "kitchen_type": "veg", "pincode": int(TEST_PIN), "state": "TestState"})
body = call("provider2 create package", "POST", "/menu/package", token=P2,
            json={"category_id": CATEGORY_ID, "package_name": f"E2E Premium Thali {RUN}",
                  "short_description": "Premium test thali", "meal_type": "lunch",
                  "food_type": "veg", "price": 150,
                  "is_subscription_available": True, "subscription_price": 150,
                  "items": [{"item_name": "Paneer", "quantity": "1 bowl"}]})
PKG2 = None
if body:
    PKG2 = body.get("package_id") or (body.get("package") or {}).get("package_id")
call("provider2 set capacity", "PUT", "/provider-package/capacity", token=P2,
     json={"provider_id": P2_ID, "package_id": PKG2, "daily_capacity": 50})

# ════════════════════════════════════════════════════════════
# USER — onboarding, browsing, cart, wallet, payments
# ════════════════════════════════════════════════════════════
section("USER: onboarding, browsing, cart, wallet")

body = call("user generate otp", "POST", "/user/auth/generate-otp",
            json={"phone": U1_PHONE, "password": PASSWORD}, check=ok)
U1_OTP = (body or {}).get("otp")
call("user verify wrong otp", "POST", "/user/auth/verify-otp",
     json={"phone": U1_PHONE, "otp": "000000"}, expect=(400, 422))
call("user verify otp", "POST", "/user/auth/verify-otp",
     json={"phone": U1_PHONE, "otp": U1_OTP})
body = call("user login", "POST", "/user/auth/login",
            json={"phone": U1_PHONE, "password": PASSWORD})
U1 = body.get("access_token") if body else None

call("user profile get", "GET", "/user/profile", token=U1)
call("user profile update", "PUT", "/user/profile", token=U1,
     json={"full_name": "E2E Customer", "gender": "male"})
call("user profile image", "PUT", "/user/profile/image", token=U1,
     files={"file": ("me.png", PNG, "image/png")})

body = call("user create address", "POST", "/user/address", token=U1,
            json={"label": "Home", "address_line1": "55 Test Lane", "city": "Testville",
                  "state": "TestState", "pin_code": TEST_PIN, "is_default": True})
ADDR = None
if body:
    ADDR = body.get("address_id") or (body.get("address") or {}).get("user_address_id") \
        or (body.get("address") or {}).get("address_id")
body = call("user list addresses", "GET", "/user/address", token=U1)
if not ADDR and body:
    lst = body.get("addresses") or []
    ADDR = (lst[0].get("user_address_id") or lst[0].get("address_id")) if lst else None
call("user address detail", "GET", "/user/address/{aid}", token=U1, path={"aid": ADDR})
call("user address update", "PUT", "/user/address/{aid}", token=U1, path={"aid": ADDR},
     json={"landmark": "Blue gate"})
body = call("user create 2nd address", "POST", "/user/address", token=U1,
            json={"label": "Work", "address_line1": "9 Office Rd", "city": "Testville",
                  "state": "TestState", "pin_code": TEST_PIN})
ADDR2 = None
if body:
    ADDR2 = body.get("address_id") or (body.get("address") or {}).get("user_address_id") \
        or (body.get("address") or {}).get("address_id")
if ADDR2:
    call("user delete 2nd address", "DELETE", "/user/address/{aid}", token=U1, path={"aid": ADDR2})

call("user browse packages by pincode", "GET", "/user/menu/packages", token=U1,
     params={"pin_code": TEST_PIN})
call("user package detail", "GET", "/user/menu/packages/{pid}", token=U1, path={"pid": PKG1})

body = call("user add to cart", "POST", "/user/cart", token=U1,
            json={"package_id": PKG1, "quantity": 2})
CART_ITEM = (body or {}).get("cart_item_id") or ((body or {}).get("item") or {}).get("cart_item_id")
body = call("user get cart", "GET", "/user/cart", token=U1)
if not CART_ITEM and body:
    items = body.get("items") or []
    CART_ITEM = items[0].get("cart_item_id") if items else None
if CART_ITEM:
    call("user update cart item", "PUT", "/user/cart/{cid}", token=U1,
         path={"cid": CART_ITEM}, json={"quantity": 1})
    call("user remove cart item", "DELETE", "/user/cart/{cid}", token=U1, path={"cid": CART_ITEM})
call("user add to cart again", "POST", "/user/cart", token=U1,
     json={"package_id": PKG1, "quantity": 1})
call("user clear cart", "DELETE", "/user/cart/clear", token=U1)

call("user wallet before recharge (404 by design)", "GET", "/user/wallet", token=U1,
     expect=404)
call("user wallet recharge", "POST", "/user/wallet/recharge", token=U1,
     json={"amount": 5000, "description": "E2E recharge"})
call("user wallet get", "GET", "/user/wallet", token=U1)
call("user wallet transactions", "GET", "/user/wallet/transactions", token=U1)

body = call("user payment initiate", "POST", "/user/payment/initiate", token=U1,
            json={"amount": 500})
PAYMENT_ID = (body or {}).get("payment_id")
if PAYMENT_ID:
    call("user payment confirm", "POST", "/user/payment/{pid}/confirm", token=U1,
         path={"pid": PAYMENT_ID}, json={"gateway_txn_id": f"TXN{RUN}"})
call("user payments list", "GET", "/user/payment", token=U1)
if PAYMENT_ID:
    call("user payment detail", "GET", "/user/payment/{pid}", token=U1, path={"pid": PAYMENT_ID})

# ════════════════════════════════════════════════════════════
# USER — subscriptions (create, pause/resume, switch, cancel)
# ════════════════════════════════════════════════════════════
section("USER: subscriptions")

call("plan options", "GET", "/user/subscription/plans/options", token=U1)
call("plans list", "GET", "/user/subscription/plans", token=U1,
     params={"meal_slot": "lunch", "subscription_type": "weekly"})

body = call("user create subscription", "POST", "/user/subscription", token=U1,
            json={"vendor_id": P1_ID, "plan_id": PLAN_ID, "address_id": ADDR,
                  "start_date": str(TODAY),
                  "items": [{"package_id": PKG1, "quantity": 1}]}, check=ok)
SUB1 = (body or {}).get("subscription_id")

call("user list subscriptions", "GET", "/user/subscription", token=U1)
call("user subscribed packages", "GET", "/user/subscription/packages", token=U1)
call("user subscription detail", "GET", "/user/subscription/{sid}", token=U1, path={"sid": SUB1})
call("user foreign subscription detail", "GET", "/user/subscription/{sid}",
     token=U1, path={"sid": "00000000-0000-0000-0000-000000000000"}, expect=404)

print("  -> running order generator scheduler")
run_order_scheduler()

call("switch preview same package rejected", "POST", "/user/subscription/{sid}/switch/preview",
     token=U1, path={"sid": SUB1}, json={"new_package_id": PKG1}, expect=400)
body = call("switch preview to provider2", "POST", "/user/subscription/{sid}/switch/preview",
            token=U1, path={"sid": SUB1}, json={"new_package_id": PKG2}, check=ok)
body = call("switch execute to provider2", "POST", "/user/subscription/{sid}/switch",
            token=U1, path={"sid": SUB1}, json={"new_package_id": PKG2}, check=ok)
SUB2 = (body or {}).get("new_subscription_id")
call("switch again on switched sub rejected", "POST", "/user/subscription/{sid}/switch",
     token=U1, path={"sid": SUB1}, json={"new_package_id": PKG2}, expect=400)

if SUB2:
    call("user pause subscription", "PUT", "/user/subscription/{sid}/pause", token=U1,
         path={"sid": SUB2})
    call("user resume subscription", "PUT", "/user/subscription/{sid}/resume", token=U1,
         path={"sid": SUB2})
    call("user resume active sub rejected", "PUT", "/user/subscription/{sid}/resume",
         token=U1, path={"sid": SUB2}, expect=400)

# separate short subscription for the cancel flow
body = call("user create subscription 2", "POST", "/user/subscription", token=U1,
            json={"vendor_id": P1_ID, "plan_id": PLAN_ID, "address_id": ADDR,
                  "start_date": str(TODAY + timedelta(days=1)),
                  "items": [{"package_id": PKG1, "quantity": 1}]})
SUB3 = (body or {}).get("subscription_id")
if SUB3:
    call("user cancel subscription", "PUT", "/user/subscription/{sid}/cancel", token=U1,
         path={"sid": SUB3}, json={"cancel_reason": "E2E test cancel"})
    call("user cancel twice rejected", "PUT", "/user/subscription/{sid}/cancel", token=U1,
         path={"sid": SUB3}, json={"cancel_reason": "again"}, expect=400)

# ════════════════════════════════════════════════════════════
# USER — extra (one-time) order
# ════════════════════════════════════════════════════════════
section("USER: extra order")

body = call("user place extra order", "POST", "/user/order/extra", token=U1,
            json={"vendor_id": P1_ID, "address_id": ADDR, "delivery_date": str(TODAY),
                  "meal_slot": "dinner", "items": [{"package_id": PKG1, "quantity": 1}]})
_orders = (body or {}).get("orders") or []
EXTRA_ORDER = _orders[0].get("extra_order_id") if _orders else None
call("user extra orders list", "GET", "/user/order/extra", token=U1)
if EXTRA_ORDER:
    call("user extra order detail", "GET", "/user/order/extra/{oid}", token=U1,
         path={"oid": EXTRA_ORDER})

# ════════════════════════════════════════════════════════════
# DELIVERY BOY — onboarding
# ════════════════════════════════════════════════════════════
section("DELIVERY BOY: onboarding")

body = call("delivery register", "POST", "/delivery/auth/register",
            json={"mobile_number": D1_MOBILE, "password": PASSWORD}, check=ok)
D1_OTP = (body or {}).get("otp")
call("delivery verify wrong otp", "POST", "/delivery/auth/verify-otp",
     json={"mobile_number": D1_MOBILE, "otp": "000000"}, expect=400)
body = call("delivery verify otp", "POST", "/delivery/auth/verify-otp",
            json={"mobile_number": D1_MOBILE, "otp": D1_OTP}, check=ok)
body = call("delivery login", "POST", "/delivery/auth/login",
            json={"mobile_number": D1_MOBILE, "password": PASSWORD}, check=ok)
D1 = body.get("access_token") if body else None
D1_ID = body.get("delivery_boy_id") if body else None

call("delivery profile get", "GET", "/delivery/profile", token=D1)
call("delivery profile update", "PUT", "/delivery/profile", token=D1,
     json={"full_name": "E2E Rider", "vehicle_type": "bike",
           "vehicle_number": f"TS09{RUN[-4:]}", "is_online": True})
call("delivery upload document", "POST", "/delivery/documents", token=D1,
     data={"document_type": "aadhaar"}, files={"file": ("aadhaar.png", PNG, "image/png")})
call("delivery upload bad doc type", "POST", "/delivery/documents", token=D1,
     data={"document_type": "passport"}, files={"file": ("x.png", PNG, "image/png")},
     expect=400)
call("delivery list documents", "GET", "/delivery/documents", token=D1)
call("delivery payout save", "PUT", "/delivery/payout-details", token=D1,
     json={"account_holder_name": "E2E Rider", "upi_id": "e2e@upi"})
call("delivery payout get", "GET", "/delivery/payout-details", token=D1)

call("admin assign provider to delivery boy", "PUT",
     "/admin/delivery-boys/{did}/assign-provider", token=ADMIN,
     path={"did": D1_ID}, params={"provider_id": P1_ID})
call("admin update delivery boy", "PUT", "/admin/delivery-boys/{did}", token=ADMIN,
     path={"did": D1_ID}, json={"is_active": True})

# ════════════════════════════════════════════════════════════
# PROVIDER — orders visibility & assignment
# ════════════════════════════════════════════════════════════
section("PROVIDER: orders & assignment")

# after the switch, today's lunch order belongs to provider 1 (served today), so
# provider 1 sees today's subscription order; the extra order is also theirs.
call("provider subscriptions list", "GET", "/provider/orders/subscriptions", token=P1)
body = call("provider sub orders today", "GET", "/provider/orders/subscription-orders",
            token=P1, params={"order_date": str(TODAY)})
orders = (body or {}).get("orders") or []
SUB_ORDER = orders[0].get("order_id") if orders else None
if SUB_ORDER:
    call("provider set sub order preparing", "PUT",
         "/provider/orders/subscription-orders/{oid}/status", token=P1,
         path={"oid": SUB_ORDER}, json={"status": "preparing"})
    call("provider invalid order status", "PUT",
         "/provider/orders/subscription-orders/{oid}/status", token=P1,
         path={"oid": SUB_ORDER}, json={"status": "flying"}, expect=400)
    call("provider assign delivery boy (sub order)", "PUT",
         "/provider/orders/subscription-orders/{oid}/assign-delivery-boy", token=P1,
         path={"oid": SUB_ORDER}, json={"delivery_boy_id": D1_ID})
call("provider food summary", "GET", "/provider/orders/food-summary", token=P1,
     params={"summary_date": str(TODAY)})

body = call("provider extra orders", "GET", "/provider/orders/extra", token=P1,
            params={"delivery_date": str(TODAY)})
extra = (body or {}).get("orders") or []
if EXTRA_ORDER is None and extra:
    EXTRA_ORDER = extra[0].get("extra_order_id") or extra[0].get("order_id")
if EXTRA_ORDER:
    call("provider set extra order preparing", "PUT",
         "/provider/orders/extra/{oid}/status", token=P1,
         path={"oid": EXTRA_ORDER}, json={"status": "preparing"})
    call("provider assign delivery boy (extra)", "PUT",
         "/provider/orders/extra/{oid}/assign-delivery-boy", token=P1,
         path={"oid": EXTRA_ORDER}, json={"delivery_boy_id": D1_ID})

SUB_FOR_DETAIL = SUB1
if SUB_FOR_DETAIL:
    call("provider subscription detail", "GET",
         "/provider/orders/subscriptions/{sid}", token=P1, path={"sid": SUB_FOR_DETAIL})

# ════════════════════════════════════════════════════════════
# DELIVERY BOY — pickup & deliver
# ════════════════════════════════════════════════════════════
section("DELIVERY BOY: pickup & deliver")

call("delivery orders today", "GET", "/delivery/orders", token=D1,
     params={"order_date": str(TODAY)})
if SUB_ORDER:
    call("delivery sub order detail", "GET", "/delivery/orders/{oid}", token=D1,
         path={"oid": SUB_ORDER})
    call("delivery deliver before pickup rejected", "PUT",
         "/delivery/orders/{oid}/deliver", token=D1, path={"oid": SUB_ORDER},
         json={"otp": "000000"}, expect=400)
    call("delivery pickup sub order", "PUT", "/delivery/orders/{oid}/pickup", token=D1,
         path={"oid": SUB_ORDER}, json={"delivery_notes": "picked"})
    call("delivery deliver wrong otp", "PUT", "/delivery/orders/{oid}/deliver", token=D1,
         path={"oid": SUB_ORDER}, json={"otp": "000000"}, expect=400)
    otp = get_order_otp(SUB_ORDER)
    call("delivery deliver sub order", "PUT", "/delivery/orders/{oid}/deliver", token=D1,
         path={"oid": SUB_ORDER}, json={"otp": otp, "delivery_notes": "done"})

call("delivery extra orders today", "GET", "/delivery/extra-orders", token=D1,
     params={"delivery_date": str(TODAY)})
if EXTRA_ORDER:
    call("delivery extra order detail", "GET", "/delivery/extra-orders/{oid}", token=D1,
         path={"oid": EXTRA_ORDER})
    call("delivery pickup extra order", "PUT", "/delivery/extra-orders/{oid}/pickup",
         token=D1, path={"oid": EXTRA_ORDER}, json={"delivery_notes": "picked"})
    call("delivery deliver extra order", "PUT", "/delivery/extra-orders/{oid}/deliver",
         token=D1, path={"oid": EXTRA_ORDER}, json={"delivery_notes": "done"})

call("delivery wallet", "GET", "/delivery/wallet", token=D1)
call("delivery wallet transactions", "GET", "/delivery/wallet/transactions", token=D1)
call("delivery earnings", "GET", "/delivery/earnings", token=D1)
body = call("delivery notifications", "GET", "/delivery/notifications", token=D1)
notifs = (body or {}).get("notifications") or []
if notifs:
    call("delivery mark notification read", "PUT",
         "/delivery/notifications/{nid}/read", token=D1,
         path={"nid": notifs[0].get("delivery_boy_notification_id")})
call("delivery notifications read-all", "PUT", "/delivery/notifications/read-all", token=D1)

# ════════════════════════════════════════════════════════════
# WALLET/BILLING + provider wallet
# ════════════════════════════════════════════════════════════
section("PROVIDER: wallet & billing")

print("  -> running billing scheduler:", run_billing_scheduler())
call("provider wallet", "GET", "/provider/wallet", token=P1)
call("provider wallet transactions", "GET", "/provider/wallet/transactions", token=P1)
call("provider withdraw too much", "POST", "/provider/wallet/withdraw", token=P1,
     json={"amount": 10_000_000, "description": "too much"}, expect=400)

# ════════════════════════════════════════════════════════════
# REVIEWS & COMPLAINTS (all roles)
# ════════════════════════════════════════════════════════════
section("REVIEWS & COMPLAINTS")

body = call("user create review", "POST", "/user/review", token=U1,
            json={"vendor_id": P1_ID, "vendor_rating": 4, "package_rating": 5,
                  "review_text": "E2E: tasty!", "package_id": PKG1})
REVIEW = (body or {}).get("review_id") or ((body or {}).get("review") or {}).get("review_id")
call("user reviews list", "GET", "/user/review", token=U1)
if REVIEW:
    call("user review detail", "GET", "/user/review/{rid}", token=U1, path={"rid": REVIEW})
    call("user review update", "PUT", "/user/review/{rid}", token=U1, path={"rid": REVIEW},
         json={"vendor_rating": 5})
call("vendor reviews public", "GET", "/user/review/vendor/{vid}", token=U1, path={"vid": P1_ID})

body = call("user create complaint", "POST", "/user/complaint", token=U1,
            json={"against": "vendor", "subject": "E2E complaint",
                  "description": "Food arrived late", "vendor_id": P1_ID})
U_COMPLAINT = (body or {}).get("complaint_id") or ((body or {}).get("complaint") or {}).get("complaint_id")
call("user complaints list", "GET", "/user/complaint", token=U1)
if U_COMPLAINT:
    call("user complaint detail", "GET", "/user/complaint/{cid}", token=U1, path={"cid": U_COMPLAINT})
    call("user complaint update", "PUT", "/user/complaint/{cid}", token=U1,
         path={"cid": U_COMPLAINT}, json={"description": "Food arrived very late"})

body = call("provider create complaint", "POST", "/provider/complaint", token=P1,
            json={"against": "delivery_boy", "subject": "E2E provider complaint",
                  "description": "Rider was late for pickup", "delivery_boy_id": D1_ID})
P_COMPLAINT = (body or {}).get("complaint_id") or ((body or {}).get("complaint") or {}).get("provider_complaint_id")
call("provider complaints list", "GET", "/provider/complaint", token=P1)
if P_COMPLAINT:
    call("provider complaint detail", "GET", "/provider/complaint/{cid}", token=P1,
         path={"cid": P_COMPLAINT})
    call("provider complaint update", "PUT", "/provider/complaint/{cid}", token=P1,
         path={"cid": P_COMPLAINT}, json={"description": "Rider was 40 minutes late"})

body = call("delivery create complaint", "POST", "/delivery/complaint", token=D1,
            json={"against": "provider", "subject": "E2E delivery complaint",
                  "description": "Kitchen keeps me waiting", "provider_id": P1_ID})
D_COMPLAINT = (body or {}).get("complaint_id") or ((body or {}).get("complaint") or {}).get("delivery_boy_complaint_id")
call("delivery complaints list", "GET", "/delivery/complaint", token=D1)
if D_COMPLAINT:
    call("delivery complaint detail", "GET", "/delivery/complaint/{cid}", token=D1,
         path={"cid": D_COMPLAINT})
    call("delivery complaint update", "PUT", "/delivery/complaint/{cid}", token=D1,
         path={"cid": D_COMPLAINT}, json={"description": "Waited 30 minutes"})

# user notifications (switch + others should exist by now)
body = call("user notifications", "GET", "/user/notification", token=U1)
u_notifs = (body or {}).get("notifications") or []
if u_notifs:
    call("user mark notification read", "PUT", "/user/notification/{nid}/read", token=U1,
         path={"nid": u_notifs[0].get("notification_id")})
call("user notifications read-all", "PUT", "/user/notification/read-all", token=U1)

# ════════════════════════════════════════════════════════════
# ADMIN — management over the data created above
# ════════════════════════════════════════════════════════════
section("ADMIN: management")

call("admin users list", "GET", "/admin/users", token=ADMIN, params={"search": U1_PHONE})
body = call("admin users find", "GET", "/admin/users", token=ADMIN, params={"search": U1_PHONE})
USER_ID = None
if body:
    lst = body.get("users") or []
    USER_ID = lst[0].get("user_id") if lst else None
if USER_ID:
    call("admin user detail", "GET", "/admin/users/{uid}", token=ADMIN, path={"uid": USER_ID})
    call("admin user wallet adjust", "POST", "/admin/users/{uid}/wallet/adjust", token=ADMIN,
         path={"uid": USER_ID}, json={"amount": 100, "type": "credit",
                                      "reason": "goodwill", "description": "E2E adjust"})
    call("admin user status", "PUT", "/admin/users/{uid}/status", token=ADMIN,
         path={"uid": USER_ID}, json={"status": "active", "reason": "E2E"})

call("admin providers list", "GET", "/admin/providers", token=ADMIN, params={"search": "E2E Kitchen"})
call("admin provider detail", "GET", "/admin/providers/{pid}", token=ADMIN, path={"pid": P1_ID})
call("admin provider update", "PUT", "/admin/providers/{pid}", token=ADMIN,
     path={"pid": P1_ID}, json={"business_name": "E2E Kitchen One Updated"})
call("admin provider accepting-orders off/on", "PUT",
     "/admin/providers/{pid}/accepting-orders", token=ADMIN,
     path={"pid": P1_ID}, params={"accepting": True})
call("admin deactivate provider with active subs rejected", "PUT",
     "/admin/providers/{pid}/deactivate", token=ADMIN, path={"pid": P2_ID}, expect=400)
UNAVAIL_DATE = str(TODAY + timedelta(days=3))
call("admin provider add unavailability", "POST",
     "/admin/providers/{pid}/unavailability", token=ADMIN,
     path={"pid": P1_ID}, json={"date": UNAVAIL_DATE, "reason": "E2E holiday"})
call("admin provider list unavailability", "GET",
     "/admin/providers/{pid}/unavailability", token=ADMIN, path={"pid": P1_ID})
call("admin provider delete unavailability", "DELETE",
     "/admin/providers/{pid}/unavailability/{d}", token=ADMIN,
     path={"pid": P1_ID, "d": UNAVAIL_DATE})
call("admin provider wallet adjust", "POST", "/admin/providers/{pid}/wallet/adjust",
     token=ADMIN, path={"pid": P1_ID},
     json={"amount": 50, "type": "credit", "reason": "promo", "description": "E2E"})

call("admin delivery boys list", "GET", "/admin/delivery-boys", token=ADMIN,
     params={"search": "E2E Rider"})
call("admin delivery boy detail", "GET", "/admin/delivery-boys/{did}", token=ADMIN,
     path={"did": D1_ID})

body = call("admin create package (predefined)", "POST", "/admin/packages", token=ADMIN,
            json={"category_id": CATEGORY_ID, "package_name": f"E2E Admin Package {RUN}",
                  "meal_type": "lunch", "food_type": "veg", "price": 120,
                  "items": [{"item_name": "Rice", "quantity": "1"}]})
ADMIN_PKG = None
if body:
    ADMIN_PKG = body.get("package_id") or (body.get("package") or {}).get("package_id")
call("admin packages list", "GET", "/admin/packages", token=ADMIN, params={"search": "E2E"})
if ADMIN_PKG:
    call("admin package detail", "GET", "/admin/packages/{pid}", token=ADMIN, path={"pid": ADMIN_PKG})
    call("admin package update", "PUT", "/admin/packages/{pid}", token=ADMIN,
         path={"pid": ADMIN_PKG}, json={"price": 125})
    # true happy path for provider package selection: a predefined package
    call("provider2 select predefined package", "POST", "/provider-package/select", token=P2,
         json={"provider_id": P2_ID, "package_id": ADMIN_PKG, "daily_capacity": 20})
    call("admin package delete", "DELETE", "/admin/packages/{pid}", token=ADMIN,
         path={"pid": ADMIN_PKG})

call("admin subscriptions list", "GET", "/admin/orders/subscriptions", token=ADMIN,
     params={"vendor_id": P1_ID})
call("admin sub orders list", "GET", "/admin/orders/subscription-orders", token=ADMIN,
     params={"order_date": str(TODAY)})
call("admin extra orders list", "GET", "/admin/orders/extra-orders", token=ADMIN,
     params={"delivery_date": str(TODAY)})

# order intervention endpoints on a future (scheduled) order of SUB2 (vendor = P2)
FUTURE_ORDER = FUTURE_DATE = None
try:
    from app.core.database import SessionLocal
    from app.models.order_model import Order
    _db = SessionLocal()
    _o = (_db.query(Order)
          .filter(Order.subscription_reference_id == SUB2,
                  Order.status == "scheduled")
          .order_by(Order.order_date.asc()).first())
    if _o:
        FUTURE_ORDER, FUTURE_DATE = str(_o.order_id), str(_o.order_date)
    _db.close()
except Exception as e:
    print("  !! could not fetch future order:", e)

if FUTURE_ORDER:
    call("admin assign delivery boy (sub order)", "PUT",
         "/admin/orders/subscription-orders/{oid}/assign-delivery-boy", token=ADMIN,
         path={"oid": FUTURE_ORDER}, json={"delivery_boy_id": D1_ID, "reason": "E2E"})
    call("admin reassign without unavailability rejected", "PUT",
         "/admin/orders/subscription-orders/{oid}/reassign-provider", token=ADMIN,
         path={"oid": FUTURE_ORDER}, json={"new_provider_id": P1_ID, "reason": "E2E"},
         expect=400)
    call("admin mark P2 unavailable on order date", "POST",
         "/admin/providers/{pid}/unavailability", token=ADMIN,
         path={"pid": P2_ID}, json={"date": FUTURE_DATE, "reason": "E2E reassign test"})
    call("admin reassign provider (sub order)", "PUT",
         "/admin/orders/subscription-orders/{oid}/reassign-provider", token=ADMIN,
         path={"oid": FUTURE_ORDER}, json={"new_provider_id": P1_ID, "reason": "E2E"})
    call("admin sub order status", "PUT",
         "/admin/orders/subscription-orders/{oid}/status", token=ADMIN,
         path={"oid": FUTURE_ORDER}, json={"status": "cancelled", "reason": "E2E"})

# second extra order for admin intervention endpoints
body = call("user place extra order 2", "POST", "/user/order/extra", token=U1,
            json={"vendor_id": P1_ID, "address_id": ADDR,
                  "delivery_date": str(TODAY + timedelta(days=1)),
                  "meal_slot": "lunch", "items": [{"package_id": PKG1, "quantity": 1}]})
_orders = (body or {}).get("orders") or []
EXTRA2 = _orders[0].get("extra_order_id") if _orders else None
if EXTRA2:
    EXTRA2_DATE = str(TODAY + timedelta(days=1))
    call("admin assign delivery boy (extra)", "PUT",
         "/admin/orders/extra-orders/{oid}/assign-delivery-boy", token=ADMIN,
         path={"oid": EXTRA2}, json={"delivery_boy_id": D1_ID, "reason": "E2E"})
    # reassign P1 -> P2 requires: P1 unavailable that date, P2 NOT unavailable
    call("admin clear P2 unavailability for reassign target date", "DELETE",
         "/admin/providers/{pid}/unavailability/{d}", token=ADMIN,
         path={"pid": P2_ID, "d": EXTRA2_DATE}, expect=(200, 404))
    call("admin mark P1 unavailable on extra order date", "POST",
         "/admin/providers/{pid}/unavailability", token=ADMIN,
         path={"pid": P1_ID}, json={"date": EXTRA2_DATE, "reason": "E2E extra reassign"})
    call("admin reassign provider (extra)", "PUT",
         "/admin/orders/extra-orders/{oid}/reassign-provider", token=ADMIN,
         path={"oid": EXTRA2}, json={"new_provider_id": P2_ID, "reason": "E2E"})
    call("admin extra order status", "PUT",
         "/admin/orders/extra-orders/{oid}/status", token=ADMIN,
         path={"oid": EXTRA2}, json={"status": "cancelled", "reason": "E2E"})
    call("admin clear P1 unavailability again", "DELETE",
         "/admin/providers/{pid}/unavailability/{d}", token=ADMIN,
         path={"pid": P1_ID, "d": EXTRA2_DATE}, expect=(200, 404))

if SUB2:
    call("admin cancel user subscription", "PUT",
         "/admin/users/subscriptions/{sid}/cancel", token=ADMIN,
         path={"sid": SUB2}, params={"reason": "E2E admin cancel"})

# with P2's only subscription cancelled, deactivate/activate now succeeds
call("admin provider deactivate", "PUT", "/admin/providers/{pid}/deactivate", token=ADMIN,
     path={"pid": P2_ID})
call("admin provider activate", "PUT", "/admin/providers/{pid}/activate", token=ADMIN,
     path={"pid": P2_ID})

call("admin payments list", "GET", "/admin/payments", token=ADMIN)
if PAYMENT_ID:
    call("admin payment detail", "GET", "/admin/payments/{pid}", token=ADMIN,
         path={"pid": PAYMENT_ID})
    call("admin payment refund", "PUT", "/admin/payments/{pid}/refund", token=ADMIN,
         path={"pid": PAYMENT_ID}, json={"refund_amount": 100, "reason": "E2E refund"})

call("admin complaints list", "GET", "/admin/complaints", token=ADMIN)
if U_COMPLAINT:
    call("admin user complaint detail", "GET", "/admin/complaints/user/{cid}", token=ADMIN,
         path={"cid": U_COMPLAINT})
    call("admin resolve user complaint", "PUT",
         "/admin/complaints/user/{cid}/resolve", token=ADMIN,
         path={"cid": U_COMPLAINT}, json={"status": "resolved", "resolution": "E2E resolved"})
if P_COMPLAINT:
    call("admin provider complaint detail", "GET", "/admin/complaints/provider/{cid}",
         token=ADMIN, path={"cid": P_COMPLAINT})
    call("admin resolve provider complaint", "PUT",
         "/admin/complaints/provider/{cid}/resolve", token=ADMIN,
         path={"cid": P_COMPLAINT}, json={"status": "resolved", "resolution": "E2E"})
if D_COMPLAINT:
    call("admin delivery complaint detail", "GET",
         "/admin/complaints/delivery-boy/{cid}", token=ADMIN, path={"cid": D_COMPLAINT})
    call("admin resolve delivery complaint", "PUT",
         "/admin/complaints/delivery-boy/{cid}/resolve", token=ADMIN,
         path={"cid": D_COMPLAINT}, json={"status": "resolved", "resolution": "E2E"})

call("admin reviews list", "GET", "/admin/reviews", token=ADMIN, params={"vendor_id": P1_ID})
if REVIEW:
    # keep it visible so the user's own soft-delete below still finds it
    call("admin review visibility", "PUT", "/admin/reviews/{rid}/visibility", token=ADMIN,
         path={"rid": REVIEW}, params={"is_visible": True})

# complaint deletes (user withdraws) — after admin resolution these should now fail;
# create fresh ones to exercise the delete endpoints
body = call("user complaint for delete", "POST", "/user/complaint", token=U1,
            json={"against": "platform", "subject": "E2E delete me",
                  "description": "Temporary complaint for withdraw test"})
cid = (body or {}).get("complaint_id") or ((body or {}).get("complaint") or {}).get("complaint_id")
if cid:
    call("user complaint withdraw", "DELETE", "/user/complaint/{cid}", token=U1, path={"cid": cid})
body = call("provider complaint for delete", "POST", "/provider/complaint", token=P1,
            json={"against": "platform", "subject": "E2E delete me",
                  "description": "Temporary complaint for withdraw test"})
cid = (body or {}).get("complaint_id") or ((body or {}).get("complaint") or {}).get("provider_complaint_id")
if cid:
    call("provider complaint withdraw", "DELETE", "/provider/complaint/{cid}", token=P1,
         path={"cid": cid})
body = call("delivery complaint for delete", "POST", "/delivery/complaint", token=D1,
            json={"against": "platform", "subject": "E2E delete me",
                  "description": "Temporary complaint for withdraw test"})
cid = (body or {}).get("complaint_id") or ((body or {}).get("complaint") or {}).get("delivery_boy_complaint_id")
if cid:
    call("delivery complaint withdraw", "DELETE", "/delivery/complaint/{cid}", token=D1,
         path={"cid": cid})

# user deletes their own review first; admin delete then targets any remaining review
if REVIEW:
    call("user review delete", "DELETE", "/user/review/{rid}", token=U1, path={"rid": REVIEW})
body = call("admin reviews list for delete", "GET", "/admin/reviews", token=ADMIN)
admin_reviews = [r for r in ((body or {}).get("reviews") or [])
                 if r.get("review_id") != REVIEW]
if admin_reviews:
    call("admin review delete", "DELETE", "/admin/reviews/{rid}", token=ADMIN,
         path={"rid": admin_reviews[0].get("review_id")}, expect=(200, 404))

# cleanup-ish: delete provider package + pincode deactivation via delete
call("menu delete package (provider2)", "DELETE", "/menu/delete/{pid}", token=P2,
     path={"pid": PKG2}, expect=(200, 400))
if PINCODE_ID:
    call("admin delete pincode", "DELETE", "/admin/pincodes/{pid}", token=ADMIN,
         path={"pid": PINCODE_ID}, expect=(200, 400))

# ════════════════════════════════════════════════════════════
# LOGOUTS
# ════════════════════════════════════════════════════════════
section("LOGOUTS")
call("provider logout", "POST", "/auth/logout", token=P1)
call("user logout", "POST", "/user/auth/logout", token=U1)
call("delivery logout", "POST", "/delivery/auth/logout", token=D1)
call("admin logout", "POST", "/admin/auth/logout", token=ADMIN)

# ════════════════════════════════════════════════════════════
# REPORT
# ════════════════════════════════════════════════════════════
section("REPORT")

passed = [r for r in results if r[0] == "PASS"]
failed = [r for r in results if r[0] == "FAIL"]
print(f"\nTOTAL: {len(results)}  PASS: {len(passed)}  FAIL: {len(failed)}")

if failed:
    print("\nFAILURES:")
    for r in failed:
        print(f"  [{r[4]} exp {r[5]}] {r[2]} {r[3]} — {r[1]}\n      {r[6]}")

# coverage vs live OpenAPI spec (normalize {param} names, which differ per side)
import re as _re


def _norm(p):
    return _re.sub(r"\{[^}]+\}", "{}", p)


try:
    requests.get(f"{BASE}/", timeout=10)
    covered.add(("GET", "/"))
    spec = requests.get(f"{BASE}/openapi.json", timeout=10).json()
    all_ops = {(m.upper(), _norm(path))
               for path, methods in spec["paths"].items() for m in methods}
    covered_norm = {(m, _norm(p)) for m, p in covered}
    missed = sorted(all_ops - covered_norm)
    print(f"\nCOVERAGE: {len(covered_norm & all_ops)}/{len(all_ops)} operations hit")
    if missed:
        print("NOT COVERED:")
        for m, p in missed:
            print(f"  {m} {p}")
except Exception as e:
    print("coverage check failed:", e)

sys.exit(1 if failed else 0)
