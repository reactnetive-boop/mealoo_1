"""Generate role-based API reference markdown files from the live OpenAPI spec."""
import json
import re
import urllib.request
from pathlib import Path

SPEC_URL = "http://localhost:8000/openapi.json"
OUT_DIR = Path(r"D:\mealoo\docs\api")

# tag -> (endpoint file, service file(s))
SOURCES = {
    "Provider Auth": ("app/api/v1/endpoints/auth.py", "app/services/auth_service.py, app/services/otp_service.py"),
    "Provider": ("app/api/v1/endpoints/provider.py", "app/services/provider_service.py"),
    "Provider Menu": ("app/api/v1/endpoints/menu.py, app/api/v1/endpoints/provider_selected_package_endpoint.py", "app/services/menu_service.py"),
    "Provider Package Item": ("app/api/v1/endpoints/package_item.py", "app/services/package_item_service.py"),
    "Provider Package Image": ("app/api/v1/endpoints/package_image.py", "app/services/package_image_service.py"),
    "Provider Orders": ("app/api/v1/endpoints/provider_orders.py", "app/services/provider_order_service.py"),
    "Provider Wallet": ("app/api/v1/endpoints/provider_wallet.py", "app/services/provider_wallet_service.py"),
    "Provider Complaint": ("app/api/v1/endpoints/provider_complaint.py", "app/services/provider_complaint_service.py"),
    "User Authentication": ("app/api/v1/endpoints/user_auth.py", "app/services/user_auth_service.py"),
    "User Profile": ("app/api/v1/endpoints/user_profile.py", "app/services/user_profile_service.py"),
    "User Address": ("app/api/v1/endpoints/user_address.py", "app/services/user_address_service.py"),
    "User Location": ("app/api/v1/endpoints/location.py", "app/services/pincode_service.py"),
    "User Menu": ("app/api/v1/endpoints/user_menu.py", "app/services/user_menu_service.py"),
    "User Order": ("app/api/v1/endpoints/user_order.py", "app/services/extra_order_service.py"),
    "User Cart": ("app/api/v1/endpoints/user_cart.py", "app/services/cart_service.py"),
    "User Wallet": ("app/api/v1/endpoints/user_wallet.py", "app/services/wallet_service.py"),
    "User Subscription": ("app/api/v1/endpoints/user_subscription.py", "app/services/subscription_service.py"),
    "User Review": ("app/api/v1/endpoints/user_review.py", "app/services/review_service.py"),
    "User Complaint": ("app/api/v1/endpoints/user_complaint.py", "app/services/complaint_service.py"),
    "User Notification": ("app/api/v1/endpoints/user_notification.py", "app/services/notification_service.py"),
    "User Payment": ("app/api/v1/endpoints/user_payment.py", "app/services/payment_service.py"),
    "Delivery Boy Auth": ("app/api/v1/endpoints/delivery_auth.py", "app/services/delivery_boy_auth_service.py"),
    "Delivery Boy": ("app/api/v1/endpoints/delivery_orders.py", "app/services/delivery_boy_order_service.py"),
    "Delivery Boy Account": ("app/api/v1/endpoints/delivery_account.py", "app/services/delivery_boy_account_service.py"),
    "Delivery Boy Complaint": ("app/api/v1/endpoints/delivery_complaint.py", "app/services/delivery_boy_complaint_service.py"),
    "Admin Auth": ("app/api/v1/endpoints/admin_auth.py", "app/services/admin_auth_service.py"),
    "Admin Dashboard": ("app/api/v1/endpoints/admin_dashboard.py", "app/services/admin_dashboard_service.py"),
    "Admin — Users": ("app/api/v1/endpoints/admin_users.py", "app/services/admin_user_service.py"),
    "Admin — Providers": ("app/api/v1/endpoints/admin_providers.py", "app/services/admin_provider_service.py"),
    "Admin — Delivery Boys": ("app/api/v1/endpoints/admin_delivery_boys.py", "app/services/admin_delivery_boy_service.py"),
    "Admin — Packages": ("app/api/v1/endpoints/admin_packages.py", "app/services/admin_content_service.py"),
    "Admin — Plans": ("app/api/v1/endpoints/admin_plans.py", "app/services/admin_content_service.py"),
    "Admin — Complaints": ("app/api/v1/endpoints/admin_complaints.py", "app/services/admin_complaint_service.py"),
    "Admin — Reviews": ("app/api/v1/endpoints/admin_reviews.py", "app/services/admin_review_service.py"),
    "Admin — Orders": ("app/api/v1/endpoints/admin_orders.py", "app/services/admin_order_service.py"),
    "Admin — Pincodes": ("app/api/v1/endpoints/admin_pincodes.py", "app/services/pincode_service.py"),
    "Admin — Payments": ("app/api/v1/endpoints/admin_payments.py", "app/services/admin_payment_service.py"),
}

ROLE_FILES = {
    "provider": {
        "title": "Provider (Vendor / Kitchen) API Reference",
        "filename": "provider-apis.md",
        "app_note": "Consumed by the **Provider mobile app** (vendor/kitchen owners managing menus, packages, orders, wallet).",
        "tags": ["Provider Auth", "Provider", "Provider Menu", "Provider Package Item",
                 "Provider Package Image", "Provider Orders", "Provider Wallet", "Provider Complaint"],
        "extra": """## Password recovery flow (provider app)

Screens: login -> 'Forgot password?' -> OTP screen -> 'Set new password' -> back to login.

| Step | Endpoint | Body |
|---|---|---|
| 1. Send OTP | `POST /auth/forgot-password/send-otp` | `mobile_number` |
| 2. Verify OTP | `POST /auth/verify-otp` | `mobile_number`, `otp` |
| 3. Set new password | `POST /auth/forgot-password/reset` | `mobile_number`, `new_password`, `confirm_password` |
| 4. Login | `POST /auth/login` | `mobile_number`, `password` (the new one) |

Step 2 is the same endpoint registration uses - the app can reuse that screen.

**Registration vs. recovery.** `provider.otp_logs.purpose` tags every code as
`registration` or `password_reset`, and the two are not interchangeable: a registration
OTP cannot complete step 3, and verifying a `password_reset` OTP does **not** change the
account password (it only proves the provider owns the number). Registration keeps its
existing behaviour - `POST /auth/generate-otp` carries the chosen password and
`POST /auth/verify-otp` applies it.

**Rules.**

| Scenario | Behaviour |
|---|---|
| Mobile number not registered | 400 "Provider not found" |
| Provider deactivated (`is_active = false`) | 400 - contact support |
| Step 3 before step 2 | 400 "OTP not verified" |
| OTP older than 15 minutes | 400 "OTP session expired" |
| `new_password` != `confirm_password` | 400 |
| Password outside 8-16 characters | 422 (schema validation) |
| Re-using an OTP after a successful reset | 400 - the OTP is burnt on use, request a new one |
| A newer OTP requested before step 3 | Only the latest `password_reset` OTP counts |

No token is issued by step 3 - the app must send the provider back to the login screen.

**Source files.** Endpoints: `app/api/v1/endpoints/auth.py` - service:
`app/services/auth_service.py` (`forgot_password_send_otp`, `reset_password`) - schemas:
`app/schemas/auth_schema.py` - migration:
`alembic/versions/c7d8e9f0a1b2_add_purpose_to_provider_otp_logs.py`.

**Note.** OTPs are returned in the API response while SMS delivery is not wired up; drop
the `otp` field from the response once an SMS provider is integrated.

## Capacity: two limits, both enforced

A kitchen can be capped at two levels, and an incoming order must fit inside **both**.
Either one left as `null` means that level is not enforced.

| Limit | Field | Scope | Set with |
|---|---|---|---|
| Per package | `daily_capacity` on `provider_selected_packages` | One package, per meal-slot, per day | `PUT /provider-package/capacity` |
| Per provider | `daily_meal_quota` on `providers` | **All** packages together, per meal-slot, per day | `PUT /provider/daily-quota` |

`daily_meal_quota = 15` means 15 breakfasts **and** 15 lunches **and** 15 dinners a day,
whatever mix of packages those meals come from. A provider running three packages capped
at 10 each, with a quota of 15, can still only serve 15 meals in a slot.

**What counts against a slot.** Quantities from every `active` subscription whose
`meal_slot` covers that slot (`all_slots` counts towards all three), plus quantities from
non-cancelled one-time orders on the date being checked.

**Where it is enforced.** `POST /user/subscription`, `POST /user/subscription/{id}/switch`
(against the *new* provider) and `POST /user/order/extra`. All items in one request are
summed before the check, so a single order cannot straddle the limit. Over the limit
returns `400` naming the slot, the limit, what is already committed and what is left.

**Changing the limit.** A new quota below the meals already committed to active
subscriptions is rejected with `400`; the response carries that figure as
`current_peak_demand`. Lowering the limit never cancels running subscriptions - it only
stops new ones. Send `null` to remove the limit.

**Reading it.** `GET /provider/daily-quota` (provider app) and
`GET /admin/providers/{provider_id}/daily-quota` (admin panel) return, per slot,
`subscription_committed`, `extra_orders`, `total_committed`, `available` and `is_full`,
for today or any `?date=`.

**Source files.** Model: `app/models/provider_model.py` (`daily_meal_quota`) - checks:
`app/domain/capacity.py` - migration:
`alembic/versions/d8e9f0a1b2c3_add_provider_quota_and_fssai.py`.
""",
    },
    "user": {
        "title": "Customer / User API Reference",
        "filename": "user-apis.md",
        "app_note": "Consumed by the **Customer mobile app** (end users browsing menus, subscribing to meal plans, ordering, paying).",
        "tags": ["User Authentication", "User Profile", "User Address", "User Location", "User Menu",
                 "User Order", "User Cart", "User Wallet", "User Subscription", "User Review",
                 "User Complaint", "User Notification", "User Payment"],
        "extra": """## Package Switch Policy (subscription package switching)

Business rules behind `POST /user/subscription/{subscription_id}/switch/preview` and
`POST /user/subscription/{subscription_id}/switch`. Screens: package browsing → 'Switch
Package' confirmation screen (shows the preview) → success screen.

**Scope.** Same provider → different package, different provider → different package,
upgrade, downgrade, same price. All plan durations — the calculation is driven by the
subscription's actual `start_date`/`end_date`.

**Effective date rule.** A switch never takes effect the same day — today's meal is
served by the current provider. `effective_date = today + 1` (or the subscription
`start_date` if it has not begun serving yet).

**Calculation — Unused Service Value Method.** Only the remaining (unused) value of the
current subscription is compared with the remaining cost of the new package; the
customer never pays or receives the difference between full package prices.

```
Total Days         = end_date − start_date
Used Days          = (today − start_date) + 1          (includes today)
Remaining Days     = Total Days − Used Days
Old Daily Cost     = old subscription final_amount ÷ Total Days      (2 dp)
New Full Cost      = new pkg effective price × qty × meal-slot multiplier
                     × Total Days − plan discount %
New Daily Cost     = New Full Cost ÷ Total Days                      (2 dp)
Remaining Value    = Old Daily Cost × Remaining Days
New Remaining Cost = New Daily Cost × Remaining Days
Adjustment         = New Remaining Cost − Remaining Value
```

- Adjustment **> 0** (upgrade): customer pays `floor(Adjustment)` from the wallet before
  the switch completes. Insufficient balance → HTTP 400, switch cancelled, nothing changes.
- Adjustment **< 0** (downgrade): `floor(−Adjustment)` credited to the Mealoo wallet.
- Adjustment **= 0**: switch completes with no money movement.

**Rounding — Floor (Truncate) Rule.** Money moved is truncated to the nearest lower whole
rupee (₹799.92 → ₹799, ₹1200.75 → ₹1200). The signed pre-floor adjustment is kept in the
audit record.

**What executing a switch does.** Old subscription → `status = "switched"`, `end_date`
truncated to the effective date; its future scheduled orders are cancelled; a new
subscription is created for the remaining days (same plan/slot/address/free skips, new
package/provider, `final_amount = New Remaining Cost`); wallet debit
(`package_switch_payment`) or credit (`package_switch_credit`); daily orders generated;
audit row in `subscription.package_switch_logs`; notifications to the customer
(`package_switch`) and to delivery boys whose orders were cancelled (`schedule_update`).
Provider settlement is automatic — each provider is paid only for meals actually served.

**Edge cases.**

| Scenario | Behaviour |
|---|---|
| Switch on last day | Rejected — buy a new subscription instead |
| Same package selected | 400 "You are already subscribed to this package." |
| New package unavailable / not subscription-enabled | 400 rejected |
| New provider lacks capacity | 400 rejected |
| Insufficient wallet for upgrade | 400 rejected, nothing changes |
| Subscription paused / cancelled / expired | 400 — only `active` subscriptions can switch |
| Second switch of the same subscription | Impossible — status is `switched` (the new subscription can itself be switched) |
| Switch before the subscription starts serving | Used days = 0, effective from `start_date` |

**Wallet credit** from a downgrade can be used for future subscriptions, renewals,
one-time purchases, and upgrade payments; it is not withdrawable to a bank account.

**Source files.** Service: `app/services/package_switch_service.py` · audit model:
`app/models/package_switch_log_model.py` · schemas: `app/schemas/subscription_schema.py`
· migration: `alembic/versions/f4a5b6c7d8e9_add_package_switch_logs_table.py`.

## Meal Skip Policy (skipping a single subscription order)

Business rules behind `PUT /user/subscription/{subscription_id}/orders/{order_id}/skip`.
Screens: subscription detail → meal schedule (`GET .../orders`) → order detail
(`GET .../orders/{order_id}`) → 'Skip this meal' confirmation.

**What a skip does.** The order row is set to `status = "skipped"` with
`skip_requested_at`, `skip_deadline` (the cutoff for that order) and `is_free_skip`.
The provider and the assigned delivery partner (notified with `schedule_update`) do not
serve it. A skipped order cannot be un-skipped.

**Free skip = refund.** Every plan grants `free_skips_total` per subscription. A skip is
free only when **both** hold:

1. `free_skips_used < free_skips_total`, and
2. the request is **before the same-day cutoff** for the order's meal slot:

| Meal slot | Cutoff on the order date |
|---|---|
| breakfast | 06:00 |
| lunch | 09:00 |
| dinner | 15:00 |

Orders for a future date are always before the cutoff. A same-day skip after the cutoff is
still accepted but is **not free**, does **not** consume a free skip, and issues no refund
(`not_free_reason = "cutoff_passed"`). Once free skips are exhausted, further skips are
accepted without refund (`not_free_reason = "no_free_skips_left"`).

**Refund amount.** A free skip credits the per-meal amount to the Mealoo wallet and
increments `free_skips_used`:

```
Service Days     = end_date − start_date − total_days_paused
Meals Per Day    = 1 (single slot) · 2 (breakfast_lunch / lunch_dinner / breakfast_dinner) · 3 (all_slots)
Per-Meal Amount  = final_amount ÷ (Service Days × Meals Per Day)      (2 dp)
```

Wallet transaction: `type = credit`, `reason = free_skip_refund`, `reference_type = order`.

**Rules / edge cases.**

| Scenario | Behaviour |
|---|---|
| Order date is in the past | 400 "Past orders cannot be skipped" |
| Order not `scheduled` (preparing, delivered, skipped, cancelled…) | 400 |
| Subscription not `active` (paused / cancelled / expired / switched) | 400 |
| Order belongs to another subscription or user | 404 / 403 |
| Same-day skip after cutoff | Skipped, no refund, free skip not consumed |
| No free skips left | Skipped, no refund |

**Source files.** Service: `app/services/subscription_service.py` (`skip_order`,
`FREE_SKIP_CUTOFF`) · repository: `app/repositories/subscription_repository.py` · schema:
`SkipOrderResponse` in `app/schemas/subscription_schema.py`.
""",
    },
    "delivery": {
        "title": "Delivery Boy API Reference",
        "filename": "delivery-boy-apis.md",
        "app_note": (
            "Consumed by the **Delivery partner mobile app** (Expo/React Native project `Mealoo_D`, screens in `src/app/`):\n"
            "`welcome`, `register`, `verify-otp`, `login`, `complete-profile`, `upload-documents`, `vehicle-details`, "
            "`payout-details`, `application-submitted`, `home`, `orders`, `order-detail`, `navigate-provider`, "
            "`pickup-confirmation`, `pickup-otp-verification`, `navigate-customer`, `delivery-confirmation`, "
            "`delivery-success`, `wallet`, `transaction-history`, `earnings`, `notifications`, `profile`, `settings`."
        ),
        "tags": ["Delivery Boy Auth", "Delivery Boy", "Delivery Boy Account", "Delivery Boy Complaint"],
        "extra": """## Screen → API map (Mealoo_D app)

Verified against the actual imports in `Mealoo_D/src/app/*.tsx`. API wrappers live in
`src/lib/api/` (`auth.ts`, `orders.ts`, `account.ts`, `client.ts` for the base HTTP client).

| App screen | APIs called |
|---|---|
| `welcome`, `application-submitted`, `delivery-success`, `pickup-otp-verification` | none (static / navigation only) |
| `register` | POST `/delivery/auth/register` |
| `verify-otp` | POST `/delivery/auth/verify-otp`; POST `/delivery/auth/register` (resend code) |
| `login` | POST `/delivery/auth/login` |
| `complete-profile` | PUT `/delivery/profile` |
| `upload-documents` | GET `/delivery/documents`; POST `/delivery/documents` |
| `vehicle-details` | PUT `/delivery/profile` |
| `payout-details` | GET `/delivery/payout-details`; PUT `/delivery/payout-details` |
| `home` | GET `/delivery/profile`; PUT `/delivery/profile` (online toggle); GET `/delivery/orders`; GET `/delivery/extra-orders` |
| `orders` | GET `/delivery/orders`; GET `/delivery/extra-orders` |
| `order-detail`, `navigate-provider`, `navigate-customer` | GET `/delivery/orders/{order_id}`; GET `/delivery/extra-orders/{order_id}` |
| `pickup-confirmation` | PUT `/delivery/orders/{order_id}/pickup`; PUT `/delivery/extra-orders/{order_id}/pickup` |
| `delivery-confirmation` | PUT `/delivery/orders/{order_id}/deliver`; PUT `/delivery/extra-orders/{order_id}/deliver` |
| `wallet` | GET `/delivery/wallet`; GET `/delivery/wallet/transactions`; GET `/delivery/payout-details` |
| `transaction-history` | GET `/delivery/wallet`; GET `/delivery/wallet/transactions` |
| `earnings` | GET `/delivery/earnings` |
| `notifications` | GET `/delivery/notifications`; PUT `/delivery/notifications/{notification_id}/read`; PUT `/delivery/notifications/read-all` |
| `profile` | GET `/delivery/profile`; POST `/delivery/auth/logout` |
| `settings` | POST `/delivery/auth/logout` |

All paths above are relative to `/api/v1`.
""",
    },
    "admin": {
        "title": "Admin API Reference",
        "filename": "admin-apis.md",
        "app_note": "Consumed by the **Admin panel** (web dashboard for operations: user/provider/delivery-boy management, content, payments).",
        "tags": ["Admin Auth", "Admin Dashboard", "Admin — Users", "Admin — Providers", "Admin — Delivery Boys",
                 "Admin — Packages", "Admin — Plans", "Admin — Complaints", "Admin — Reviews",
                 "Admin — Orders", "Admin — Pincodes", "Admin — Payments"],
    },
}


def resolve_ref(spec, ref):
    node = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def schema_type(s, spec, depth=0):
    if not isinstance(s, dict):
        return "any"
    if "$ref" in s:
        name = s["$ref"].split("/")[-1]
        return name
    if "anyOf" in s:
        parts = [schema_type(x, spec, depth + 1) for x in s["anyOf"]]
        return " | ".join(p for p in parts if p != "null") + (" (nullable)" if "null" in parts else "")
    t = s.get("type", "any")
    if t == "array":
        return f"array of {schema_type(s.get('items', {}), spec, depth + 1)}"
    if t == "null":
        return "null"
    fmt = s.get("format")
    return f"{t} ({fmt})" if fmt else t


def body_fields(spec, op):
    rb = op.get("requestBody")
    if not rb:
        return None, None
    content = rb.get("content", {})
    for ctype, media in content.items():
        schema = media.get("schema", {})
        if "$ref" in schema:
            name = schema["$ref"].split("/")[-1]
            resolved = resolve_ref(spec, schema["$ref"])
            required = set(resolved.get("required", []))
            fields = []
            for prop, ps in resolved.get("properties", {}).items():
                req = "required" if prop in required else "optional"
                fields.append(f"`{prop}` ({schema_type(ps, spec)}, {req})")
            return ctype, fields
        return ctype, None
    return None, None


def response_model(spec, op):
    resp = op.get("responses", {}).get("200", {})
    content = resp.get("content", {})
    for media in content.values():
        schema = media.get("schema", {})
        if "$ref" in schema:
            return schema["$ref"].split("/")[-1]
        if schema.get("type") == "array" and "$ref" in schema.get("items", {}):
            return "array of " + schema["items"]["$ref"].split("/")[-1]
    return None


SCREEN_RE = re.compile(r"\*\*When to call:\*\*\s*(.+?)(?:\n\n|$)", re.S)


def extract_screen(description):
    if not description:
        return None
    m = SCREEN_RE.search(description)
    if m:
        return " ".join(m.group(1).split())
    return None


def endpoint_md(spec, path, method, op):
    lines = []
    summary = op.get("summary", "")
    lines.append(f"### `{method.upper()} {path}`" + (f" — {summary}" if summary else ""))
    lines.append("")

    desc = (op.get("description") or "").strip()

    params = [p for p in op.get("parameters", [])]
    ctype, fields = body_fields(spec, op)
    resp = response_model(spec, op)

    if desc:
        lines.append(desc)
        lines.append("")

    meta = []
    if params:
        pparts = []
        for p in params:
            loc = p.get("in")
            req = "required" if p.get("required") else "optional"
            ptype = schema_type(p.get("schema", {}), spec)
            pparts.append(f"`{p['name']}` ({loc}, {ptype}, {req})")
        meta.append("**Parameters:** " + "; ".join(pparts))
    if fields:
        meta.append(f"**Request body** ({ctype}): " + "; ".join(fields))
    elif ctype:
        meta.append(f"**Request body:** {ctype}")
    if resp:
        meta.append(f"**Response model:** `{resp}` (see `app/schemas/`)")

    lines.extend(m + "\n" for m in meta)
    return "\n".join(lines).rstrip() + "\n"


def main():
    spec = json.load(urllib.request.urlopen(SPEC_URL))
    paths = spec["paths"]

    # tag -> list of (path, method, op) preserving spec order
    by_tag = {}
    for path, methods in paths.items():
        for method, op in methods.items():
            for tag in op.get("tags", ["<untagged>"]):
                by_tag.setdefault(tag, []).append((path, method, op))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for role, cfg in ROLE_FILES.items():
        out = []
        out.append(f"# {cfg['title']}")
        out.append("")
        out.append("> Generated from the FastAPI OpenAPI spec (regenerate with `python scripts/gen_api_docs.py` if endpoints change). Base URL: `http://<host>:8000`; paths below are complete (they already include `/api/v1`).")
        out.append("")
        out.append(cfg["app_note"])
        out.append("")
        out.append("**Auth:** unless stated otherwise in the endpoint description, endpoints require the role's JWT as `Authorization: Bearer <access_token>` (obtained from the login endpoint in the Auth section).")
        out.append("")
        out.append("## Source file map")
        out.append("")
        out.append("| Tag (Swagger group) | Endpoint file | Service file |")
        out.append("|---|---|---|")
        for tag in cfg["tags"]:
            ep, svc = SOURCES.get(tag, ("?", "?"))
            out.append(f"| {tag} | {ep} | {svc} |")
        out.append("")
        out.append("Repositories live in `app/repositories/`, request/response schemas in `app/schemas/`, DB models in `app/models/`. Routers are registered with prefixes and tags in `app/api/v1/api.py`.")
        out.append("")
        if cfg.get("extra"):
            out.append(cfg["extra"])
            out.append("")

        for tag in cfg["tags"]:
            eps = by_tag.get(tag, [])
            if not eps:
                continue
            out.append(f"## {tag}")
            out.append("")
            # quick index table
            out.append("| Method | Path | Summary |")
            out.append("|---|---|---|")
            for path, method, op in eps:
                out.append(f"| {method.upper()} | `{path}` | {op.get('summary', '')} |")
            out.append("")
            for path, method, op in eps:
                out.append(endpoint_md(spec, path, method, op))
                out.append("")

        (OUT_DIR / cfg["filename"]).write_text("\n".join(out), encoding="utf-8")
        print(f"wrote {cfg['filename']}: {sum(len(by_tag.get(t, [])) for t in cfg['tags'])} endpoints")


if __name__ == "__main__":
    main()
