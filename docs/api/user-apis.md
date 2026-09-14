# Customer / User API Reference

> Generated from the FastAPI OpenAPI spec (regenerate with `python scripts/gen_api_docs.py` if endpoints change). Base URL: `http://<host>:8000`; paths below are complete (they already include `/api/v1`).

Consumed by the **Customer mobile app** (end users browsing menus, subscribing to meal plans, ordering, paying).

**Auth:** unless stated otherwise in the endpoint description, endpoints require the role's JWT as `Authorization: Bearer <access_token>` (obtained from the login endpoint in the Auth section).

## Source file map

| Tag (Swagger group) | Endpoint file | Service file |
|---|---|---|
| User Authentication | app/api/v1/endpoints/user_auth.py | app/services/user_auth_service.py |
| User Profile | app/api/v1/endpoints/user_profile.py | app/services/user_profile_service.py |
| User Address | app/api/v1/endpoints/user_address.py | app/services/user_address_service.py |
| User Location | app/api/v1/endpoints/location.py | app/services/pincode_service.py |
| User Menu | app/api/v1/endpoints/user_menu.py | app/services/user_menu_service.py |
| User Order | app/api/v1/endpoints/user_order.py | app/services/extra_order_service.py |
| User Cart | app/api/v1/endpoints/user_cart.py | app/services/cart_service.py |
| User Wallet | app/api/v1/endpoints/user_wallet.py | app/services/wallet_service.py |
| User Subscription | app/api/v1/endpoints/user_subscription.py | app/services/subscription_service.py |
| User Review | app/api/v1/endpoints/user_review.py | app/services/review_service.py |
| User Complaint | app/api/v1/endpoints/user_complaint.py | app/services/complaint_service.py |
| User Notification | app/api/v1/endpoints/user_notification.py | app/services/notification_service.py |
| User Payment | app/api/v1/endpoints/user_payment.py | app/services/payment_service.py |

Repositories live in `app/repositories/`, request/response schemas in `app/schemas/`, DB models in `app/models/`. Routers are registered with prefixes and tags in `app/api/v1/api.py`.

## Package Switch Policy (subscription package switching)

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


## User Authentication

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/user/auth/generate-otp` | Register – Step 1: Send OTP |
| POST | `/api/v1/user/auth/verify-otp` | Register – Step 2: Verify OTP |
| POST | `/api/v1/user/auth/login` | User Login |
| POST | `/api/v1/user/auth/logout` | User Logout |

### `POST /api/v1/user/auth/generate-otp` — Register – Step 1: Send OTP

**First step of user registration.**

Provide your mobile number, email, and a password. An OTP is sent to your phone. Call `/verify-otp` next with the same mobile number and the OTP received.

**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login`

**Request body** (application/json): `phone` (string (nullable), optional); `email` (string (nullable), optional); `password` (string, required)


### `POST /api/v1/user/auth/verify-otp` — Register – Step 2: Verify OTP

**Second step of user registration.**

Submit the OTP received on your mobile number to verify your account. On success the account is activated and you can log in.

**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login`

**Request body** (application/json): `phone` (string (nullable), optional); `email` (string (nullable), optional); `otp` (string, required)


### `POST /api/v1/user/auth/login` — User Login

**Login with phone number and password.**

Returns a JWT `access_token`. Include this token in the `Authorization` header as `Bearer <token>` for all authenticated endpoints.

**When to call:** After OTP verification (registration) or on every app open / session start.

**Flow:** `POST /verify-otp` → `POST /login` → use `access_token` in all subsequent calls

**Request body** (application/json): `phone` (string, required); `password` (string, required)


### `POST /api/v1/user/auth/logout` — User Logout

**Invalidate the current user session.**

Call this when the user logs out of the app. The client should discard the stored token after this call.

**Response model:** `LogoutResponse` (see `app/schemas/`)


## User Profile

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/profile` | Get My Profile |
| PUT | `/api/v1/user/profile` | Update My Profile |
| PUT | `/api/v1/user/profile/image` | Upload Profile Picture |

### `GET /api/v1/user/profile` — Get My Profile

**Fetch the logged-in user's profile details.**

Returns name, phone, email, profile image URL, and account status. Call this on app launch after login to pre-fill profile screens.

**Requires:** Bearer token from `POST /user/login`

**Response model:** `UserProfileResponse` (see `app/schemas/`)


### `PUT /api/v1/user/profile` — Update My Profile

**Update name, email, or other profile fields.**

Only the fields you send will be updated (partial update supported). Call `GET /user/profile` after to confirm the changes.

**Requires:** Bearer token from `POST /user/login`

**Request body** (application/json): `full_name` (string (nullable), optional); `gender` (string (nullable), optional); `date_of_birth` (string (date) (nullable), optional); `avatar_url` (string (nullable), optional); `email` (string (nullable), optional)


### `PUT /api/v1/user/profile/image` — Upload Profile Picture

**Upload or replace the user's profile photo.**

Send the image as `multipart/form-data` with field name `file`. Returns the new image URL. Update your local state with this URL after success.

**Requires:** Bearer token from `POST /user/login`

**Request body** (multipart/form-data): `file` (string, required)

**Response model:** `app__schemas__user_profile_schema__UpdateProfileImageResponse` (see `app/schemas/`)


## User Address

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/address` | List My Addresses |
| POST | `/api/v1/user/address` | Add Delivery Address |
| GET | `/api/v1/user/address/{address_id}` | Get Address Detail |
| PUT | `/api/v1/user/address/{address_id}` | Update Address |
| DELETE | `/api/v1/user/address/{address_id}` | Delete Address |

### `GET /api/v1/user/address` — List My Addresses

**Fetch all delivery addresses saved by the user.**

Use this to populate the address picker on the checkout / subscription screen. Each address has an `address_id` needed to create a subscription or extra order.

**Requires:** Bearer token from `POST /user/login`

**Response model:** `UserAddressListResponse` (see `app/schemas/`)


### `POST /api/v1/user/address` — Add Delivery Address

**Save a new delivery address for the user.**

Users can have multiple addresses (Home, Work, Other). The returned `address_id` (UUID) is required when creating a subscription or placing an extra order — pass it as `address_id` in those requests.

**When to call:** During onboarding or when the user adds a new address from settings.

**Flow:** Add address → use `address_id` in `POST /user/subscription` or `POST /user/order/extra`

**Request body** (application/json): `label` (string (nullable), optional); `address_line1` (string, required); `address_line2` (string (nullable), optional); `landmark` (string (nullable), optional); `city` (string, required); `state` (string, required); `pin_code` (string, required); `country` (string (nullable), optional); `latitude` (number | string (nullable), optional); `longitude` (number | string (nullable), optional); `is_default` (boolean (nullable), optional)


### `GET /api/v1/user/address/{address_id}` — Get Address Detail

**Fetch a single saved address by its ID.**

Use this to pre-fill the edit-address form.

**Requires:** Bearer token from `POST /user/login`

**Parameters:** `address_id` (path, string, required)

**Response model:** `UserAddressResponse` (see `app/schemas/`)


### `PUT /api/v1/user/address/{address_id}` — Update Address

**Edit an existing delivery address.**

Send only the fields that changed. Call `GET /user/address/{address_id}` first to get the current values for pre-filling the form.

**Requires:** Bearer token from `POST /user/login`

**Parameters:** `address_id` (path, string, required)

**Request body** (application/json): `label` (string (nullable), optional); `address_line1` (string (nullable), optional); `address_line2` (string (nullable), optional); `landmark` (string (nullable), optional); `city` (string (nullable), optional); `state` (string (nullable), optional); `pin_code` (string (nullable), optional); `country` (string (nullable), optional); `latitude` (number | string (nullable), optional); `longitude` (number | string (nullable), optional); `is_default` (boolean (nullable), optional)


### `DELETE /api/v1/user/address/{address_id}` — Delete Address

**Remove a saved delivery address.**

Cannot delete an address that is currently linked to an active subscription. Refresh the address list after deletion.

**Requires:** Bearer token from `POST /user/login`

**Parameters:** `address_id` (path, string, required)


## User Location

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/location/verify-pincode` | Check if a Pincode is Serviceable |

### `POST /api/v1/location/verify-pincode` — Check if a Pincode is Serviceable

**Verify whether Mealoo delivers to a given pincode before showing packages.**

Returns `is_serviceable: true/false` and the city/state if serviceable. Use this on the onboarding location screen or when the user changes their delivery address.

**No authentication required.**

**When to call:** Before `GET /user/menu/packages` — if not serviceable, show a 'Not available in your area' message instead of the package listing.

**Flow:** Enter pincode → `POST /location/verify-pincode` → if serviceable → `GET /user/menu/packages?pin_code=...`

**Request body** (application/json): `provider_id` (string (nullable), optional); `pincode` (integer, required); `house_no` (string (nullable), optional); `address` (string (nullable), optional); `landmark` (string (nullable), optional); `city` (string (nullable), optional); `state` (string (nullable), optional)


## User Menu

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/menu/packages` | Browse Meal Packages by Pincode |
| GET | `/api/v1/user/menu/packages/{package_id}` | Get Package Detail |

### `GET /api/v1/user/menu/packages` — Browse Meal Packages by Pincode

**Fetch all available meal packages offered by vendors in the user's area.**

Pass the user's delivery pincode as a query parameter. Only packages from vendors who service that pincode and have marked themselves available are returned.

Each item includes `package_id`, `provider_id`, pricing, meal type, and a primary image URL. Use `package_id` to fetch full details or add to cart.

**When to call:** On the home/browse screen after the user sets their delivery location.

**Flow:** Verify pincode (`POST /location/verify-pincode`) → `GET /user/menu/packages?pin_code=...` → select a package → `GET /user/menu/packages/{package_id}` for full details

**Parameters:** `pin_code` (query, integer, required)

**Response model:** `UserPackageListResponse` (see `app/schemas/`)


### `GET /api/v1/user/menu/packages/{package_id}` — Get Package Detail

**Fetch complete details of a single meal package.**

Returns package name, description, meal items list, all images, pricing, subscription availability, and food type (veg/non-veg).

**When to call:** When the user taps on a package card from the listing screen.

**Flow:** `GET /user/menu/packages` → tap package → `GET /user/menu/packages/{package_id}` → add to cart or subscribe

**Parameters:** `package_id` (path, string (uuid), required)

**Response model:** `UserPackageDetailResponse` (see `app/schemas/`)


## User Order

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/order/extra` | List My Extra Orders |
| POST | `/api/v1/user/order/extra` | Place a One-Time Extra Order |
| GET | `/api/v1/user/order/extra/{order_id}` | Get Extra Order Detail |

### `GET /api/v1/user/order/extra` — List My Extra Orders

**Fetch the complete history of one-time (extra) orders placed by the user.**

Returns order status, delivery date, meal slot, package, and amount paid. Use `order_id` from this list to get full details.

**When to call:** On the 'Order History' screen.

**Response model:** `ExtraOrderListResponse` (see `app/schemas/`)


### `POST /api/v1/user/order/extra` — Place a One-Time Extra Order

**Order a meal once without a subscription.**

This is for users who want to order on-demand rather than subscribing. Requires `package_id`, `vendor_id`, `address_id`, `meal_slot`, and `delivery_date`. Payment is deducted from the user's wallet.

**Prerequisite:** Wallet must have sufficient balance (`GET /user/wallet`). Package must be available and active.

**Flow:** Browse packages → check wallet balance → `POST /user/order/extra` → `GET /user/order/extra` to view order status

**Request body** (application/json): `vendor_id` (string (uuid), required); `address_id` (string (uuid), required); `delivery_date` (string (date), required); `meal_slot` (MealSlot, required); `items` (array of OrderItemRequest, required)

**Response model:** `PlaceOrderResponse` (see `app/schemas/`)


### `GET /api/v1/user/order/extra/{order_id}` — Get Extra Order Detail

**Fetch full details of a specific one-time order.**

Returns order status, delivery address, package items, amount, and timestamps. Use `order_id` from the `GET /user/order/extra` list response.

**When to call:** When the user taps on an order in the history list.

**Parameters:** `order_id` (path, string (uuid), required)

**Response model:** `ExtraOrderResponse` (see `app/schemas/`)


## User Cart

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/cart` | View Cart |
| POST | `/api/v1/user/cart` | Add Package to Cart |
| PUT | `/api/v1/user/cart/{cart_item_id}` | Update Cart Item Quantity |
| DELETE | `/api/v1/user/cart/{cart_item_id}` | Remove a Cart Item |
| DELETE | `/api/v1/user/cart/clear` | Clear Entire Cart |

### `GET /api/v1/user/cart` — View Cart

**Fetch all items currently in the user's cart with pricing summary.**

Returns each cart item with package name, unit price, discounted price, quantity, item total, and the cart grand total.

**When to call:** When the user opens the cart screen or before checkout.

**Flow:** `POST /user/cart` → `GET /user/cart` → review → `POST /user/subscription`

**Response model:** `CartResponse` (see `app/schemas/`)


### `POST /api/v1/user/cart` — Add Package to Cart

**Add a meal package to the user's cart.**

Send `package_id` (UUID from package listing) and `quantity` (1–10). If the same package is already in the cart, its quantity is updated instead of creating a duplicate.

**When to call:** When the user taps 'Add to Cart' on a package detail screen.

**Flow:** `GET /user/menu/packages` → `GET /user/menu/packages/{id}` → `POST /user/cart` → `GET /user/cart` → proceed to subscribe

**Request body** (application/json): `package_id` (string (uuid), required); `quantity` (integer, required)

**Response model:** `AddToCartResponse` (see `app/schemas/`)


### `PUT /api/v1/user/cart/{cart_item_id}` — Update Cart Item Quantity

**Change the quantity of an existing cart item.**

Send the new `quantity` (1–10). Use `cart_item_id` from the `GET /user/cart` response.

**When to call:** When the user taps + / – on a cart item.

**Parameters:** `cart_item_id` (path, string (uuid), required)

**Request body** (application/json): `quantity` (integer, required)

**Response model:** `AddToCartResponse` (see `app/schemas/`)


### `DELETE /api/v1/user/cart/{cart_item_id}` — Remove a Cart Item

**Remove a single item from the cart by its `cart_item_id`.**

Use `cart_item_id` from the `GET /user/cart` response. Refresh the cart after removal to update totals.

**When to call:** When the user swipes or taps 'Remove' on a specific cart item.

**Parameters:** `cart_item_id` (path, string (uuid), required)

**Response model:** `RemoveFromCartResponse` (see `app/schemas/`)


### `DELETE /api/v1/user/cart/clear` — Clear Entire Cart

**Remove all items from the user's cart at once.**

Use this on the cart screen when the user taps 'Clear Cart'. After a successful subscription creation you may also clear the cart to reset state.

**Note:** This endpoint must be called before `DELETE /user/cart/{cart_item_id}` in routing order to avoid path conflicts.

**Response model:** `ClearCartResponse` (see `app/schemas/`)


## User Wallet

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/wallet` | Get Wallet Balance |
| GET | `/api/v1/user/wallet/transactions` | Wallet Transaction History |
| POST | `/api/v1/user/wallet/recharge` | Recharge Wallet |

### `GET /api/v1/user/wallet` — Get Wallet Balance

**Fetch the user's current wallet balance.**

Always check the wallet balance before allowing the user to subscribe or place an extra order. If the balance is less than the order total, prompt the user to recharge first.

**When to call:** On the wallet screen, and before the subscription / order checkout flow.

**Response model:** `WalletDetailsResponse` (see `app/schemas/`)


### `GET /api/v1/user/wallet/transactions` — Wallet Transaction History

**Fetch all credit and debit transactions for the user's wallet.**

Each entry includes transaction type (`credit`/`debit`), amount, description, and timestamp. Use this to render the transaction history on the wallet screen.

**When to call:** When the user opens 'Transaction History' from the wallet screen.

**Response model:** `app__schemas__wallet_schema__WalletTransactionListResponse` (see `app/schemas/`)


### `POST /api/v1/user/wallet/recharge` — Recharge Wallet

**Add money to the user's wallet.**

Send `amount` (in INR). In a real implementation this would be called after a payment gateway confirms a successful transaction. Returns the updated balance.

**When to call:** After the user completes payment on the recharge screen, or when the checkout flow detects insufficient balance.

**Flow:** Check balance (`GET /user/wallet`) → insufficient → payment gateway → `POST /user/wallet/recharge` → retry subscription / order

**Request body** (application/json): `amount` (number | string, required); `description` (string (nullable), optional)

**Response model:** `WalletRechargeResponse` (see `app/schemas/`)


## User Subscription

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/subscription/plans/options` | Get Subscription Filter Options |
| GET | `/api/v1/user/subscription/plans` | List Subscription Plans |
| GET | `/api/v1/user/subscription/packages` | List My Subscribed Packages |
| GET | `/api/v1/user/subscription` | List My Subscriptions |
| POST | `/api/v1/user/subscription` | Create a New Subscription |
| GET | `/api/v1/user/subscription/{subscription_id}` | Get Subscription Detail |
| GET | `/api/v1/user/subscription/{subscription_id}/orders` | List Orders of a Subscription |
| GET | `/api/v1/user/subscription/{subscription_id}/orders/{order_id}` | Get Subscription Order Detail |
| PUT | `/api/v1/user/subscription/{subscription_id}/orders/{order_id}/skip` | Skip a Subscription Order |
| PUT | `/api/v1/user/subscription/{subscription_id}/cancel` | Cancel Subscription |
| POST | `/api/v1/user/subscription/{subscription_id}/switch/preview` | Preview a Package Switch |
| POST | `/api/v1/user/subscription/{subscription_id}/switch` | Switch to Another Package |
| PUT | `/api/v1/user/subscription/{subscription_id}/pause` | Pause Subscription |
| PUT | `/api/v1/user/subscription/{subscription_id}/resume` | Resume Paused Subscription |

### `GET /api/v1/user/subscription/plans/options` — Get Subscription Filter Options

**Fetch the distinct meal slot and subscription type values available in the system.**

Use the returned lists to populate filter dropdowns on the subscription plans screen before calling `GET /user/subscription/plans`.

**When to call:** When the user opens the 'Choose a Plan' screen for the first time.

**Response model:** `SubscriptionPlanOptionsResponse` (see `app/schemas/`)


### `GET /api/v1/user/subscription/plans` — List Subscription Plans

**Fetch available subscription plans with optional filters.**

Filter by `meal_slot` (e.g. `breakfast`, `lunch`, `all_slots`) and/or `subscription_type` (e.g. `weekly`, `monthly`). Each plan includes `plan_id`, duration in days, price, discount %, and free skips allowed.

**When to call:** After the user selects filters on the plans screen. The `plan_id` from this response is required when creating a subscription.

**Flow:** `GET /plans/options` → user selects filters → `GET /plans` → select a plan → `POST /user/subscription`

**Parameters:** `meal_slot` (query, string, optional); `subscription_type` (query, string, optional)

**Response model:** `SubscriptionPlanListResponse` (see `app/schemas/`)


### `GET /api/v1/user/subscription/packages` — List My Subscribed Packages

**Fetch all meal packages across all of the user's active subscriptions.**

Returns package details along with their linked subscription status, meal slot, and date range. Use this on the 'My Meals' or 'Active Plan' home screen.

**Requires:** Bearer token from `POST /user/login`


### `GET /api/v1/user/subscription` — List My Subscriptions

**Fetch all subscriptions (active, paused, expired, cancelled) for the logged-in user.**

Each subscription includes its status, meal slot, date range, vendor, and total amount. Use `subscription_id` to fetch detailed info or to pause / cancel.

**When to call:** On the 'My Subscriptions' screen or dashboard.

**Response model:** `SubscriptionListResponse` (see `app/schemas/`)


### `POST /api/v1/user/subscription` — Create a New Subscription

**Subscribe to one or more meal packages from a single vendor.**

**Required fields:**
- `plan_id` — from `GET /user/subscription/plans`
- `vendor_id` — `provider_id` from the package listing
- `address_id` — from `GET /user/address`
- `start_date` — when delivery should begin (YYYY-MM-DD)
- `items` — list of `{package_id, quantity}`

**What happens internally:** validates packages, checks provider capacity, calculates total after plan discount, verifies wallet balance, creates subscription + daily orders, and returns the subscription ID.

**Prerequisite:** Wallet must have sufficient balance (`GET /user/wallet`). All packages must belong to the same vendor. Each package must be subscription-enabled.

**Flow:** Browse packages → add to cart → check wallet → pick plan & address → `POST /user/subscription` → `GET /user/subscription` to confirm

**Request body** (application/json): `vendor_id` (string (uuid), required); `plan_id` (string (uuid), required); `address_id` (string (uuid), required); `start_date` (string (date), required); `items` (array of SubscriptionItemRequest, required)

**Response model:** `CreateSubscriptionResponse` (see `app/schemas/`)


### `GET /api/v1/user/subscription/{subscription_id}` — Get Subscription Detail

**Fetch full details of a single subscription by its ID.**

Returns plan info, packages, dates, status, and financial summary. Use `subscription_id` from `GET /user/subscription`.

**When to call:** When the user taps on a subscription from the list screen.

**Parameters:** `subscription_id` (path, string (uuid), required)

**Response model:** `SubscriptionResponse` (see `app/schemas/`)


### `GET /api/v1/user/subscription/{subscription_id}/orders` — List Orders of a Subscription

**Fetch every daily meal order generated for one of the user's subscriptions.**

Each subscription day is expanded into one order per meal slot (e.g. a `lunch_dinner` plan yields two orders per day). Orders are returned in date → meal-slot order and include the delivery `status`, the `otp_for_delivery` the user must share with the delivery partner, and `delivery_boy_reference_id` once assigned.

Optional filters: `status` (`scheduled`, `preparing`, `out_for_delivery`, `delivered`, `skipped`, `cancelled`) and `order_date` (YYYY-MM-DD). `status_summary` gives a per-status count for progress indicators.

**When to call:** On the 'Subscription Detail' → 'Meal Schedule' / 'Order History' screen, after `GET /user/subscription/{subscription_id}`.

**Note:** Orders are generated by the scheduler shortly after the subscription is created; an empty list right after `POST /user/subscription` is expected briefly.

**Parameters:** `subscription_id` (path, string (uuid), required); `status` (query, string, optional); `order_date` (query, string (date), optional)

**Response model:** `UserSubscriptionOrderListResponse` (see `app/schemas/`)


### `GET /api/v1/user/subscription/{subscription_id}/orders/{order_id}` — Get Subscription Order Detail

**Fetch full details of a single meal order within a subscription.**

Returns the order (status, date, meal slot, delivery OTP, delivered time), the delivery address, the subscribed packages being served, the provider (kitchen) contact info, and the assigned delivery partner (`null` until the provider assigns one).

Use `order_id` from `GET /user/subscription/{subscription_id}/orders`.

**When to call:** When the user taps an order on the meal schedule to track it or to read the OTP for hand-over.

**Parameters:** `subscription_id` (path, string (uuid), required); `order_id` (path, string (uuid), required)

**Response model:** `UserSubscriptionOrderDetailResponse` (see `app/schemas/`)


### `PUT /api/v1/user/subscription/{subscription_id}/orders/{order_id}/skip` — Skip a Subscription Order

**Skip one scheduled meal order of an active subscription.**

The order is marked `skipped` and the provider / delivery partner will not serve it. Whether the skip is **free** (meal amount refunded to the wallet) depends on two rules:

1. **Free skips left** — each plan grants `free_skips_total`; once `free_skips_used` reaches it, further skips are allowed but not refunded.
2. **Same-day cutoff** — a skip on the order's own date must be requested before **06:00** for breakfast, **09:00** for lunch, **15:00** for dinner. After the cutoff the skip still goes through but is not free and does not consume a free skip. Future dates are always before the cutoff.

A free skip credits the per-meal amount (`final_amount` ÷ serviceable meals) to the wallet with reason `free_skip_refund` and increments `free_skips_used`. `not_free_reason` (`cutoff_passed` / `no_free_skips_left`) tells the app why no refund was issued.

**Rules:** only `scheduled` orders of an `active` subscription; past dates are rejected; a skipped order cannot be un-skipped.

**When to call:** When the user taps 'Skip this meal' on the meal schedule / order detail screen (`GET /user/subscription/{subscription_id}/orders/{order_id}`). Show the cutoff and remaining free skips before confirming.

**Parameters:** `subscription_id` (path, string (uuid), required); `order_id` (path, string (uuid), required)

**Response model:** `SkipOrderResponse` (see `app/schemas/`)


### `PUT /api/v1/user/subscription/{subscription_id}/cancel` — Cancel Subscription

**Permanently cancel an active subscription.**

Provide an optional `cancel_reason` in the request body. Cancelled subscriptions cannot be reactivated — the user must create a new one.

**When to call:** When the user chooses 'Cancel Plan' from subscription settings.

**Note:** To temporarily stop deliveries, use `PUT /{subscription_id}/pause` instead.

**Parameters:** `subscription_id` (path, string (uuid), required)

**Request body** (application/json): `cancel_reason` (string (nullable), optional)


### `POST /api/v1/user/subscription/{subscription_id}/switch/preview` — Preview a Package Switch

**Calculate the cost of switching to another package without committing.**

Uses the Unused Service Value Method: the remaining (unused) value of the current package is compared with the remaining cost of the new package over the same period. The switch always becomes effective from the **next service day** — today's meal is still served by the current provider.

- `action = payment_required` → upgrade: `payment_amount` must be paid from the wallet
- `action = wallet_credit` → downgrade: `wallet_credit_amount` will be credited
- `action = no_adjustment` → same price: switch completes with no money movement

Amounts follow the Floor (Truncate) Rule — fractional paise are discarded.
Works for same-provider and different-provider switches alike.

**When to call:** On the 'Switch Package' confirmation screen, before showing the user what they will pay or receive.

**Flow:** browse packages → `POST /switch/preview` → confirm → `POST /switch`

**Parameters:** `subscription_id` (path, string (uuid), required)

**Request body** (application/json): `new_package_id` (string (uuid), required); `old_package_id` (string (uuid) (nullable), optional)

**Response model:** `PackageSwitchPreviewResponse` (see `app/schemas/`)


### `POST /api/v1/user/subscription/{subscription_id}/switch` — Switch to Another Package

**Switch the subscription to a different package (same or different provider).**

Applies the calculation shown by `POST /switch/preview`:
- **Upgrade** — the difference is debited from the wallet immediately. If the balance is insufficient the switch is cancelled and nothing changes.
- **Downgrade** — the difference (floored to whole rupees) is credited to the wallet.
- **Same price** — no money movement.

**What happens internally:** the old subscription is closed after today's service (status `switched`), its future orders are cancelled, a new subscription is created for the remaining days with the new package/provider, new daily orders are generated, an audit record is stored, and the customer plus affected delivery partners are notified. Old and new providers are each settled only for the meals they actually serve.

**Rules:** not allowed on the last day of the subscription; only active subscriptions can switch; switching to the currently subscribed package is rejected; the new package must be subscription-enabled and have capacity.

**When to call:** After the user confirms the preview on the 'Switch Package' screen.

**Parameters:** `subscription_id` (path, string (uuid), required)

**Request body** (application/json): `new_package_id` (string (uuid), required); `old_package_id` (string (uuid) (nullable), optional)

**Response model:** `PackageSwitchResponse` (see `app/schemas/`)


### `PUT /api/v1/user/subscription/{subscription_id}/pause` — Pause Subscription

**Temporarily pause an active subscription starting from tomorrow.**

All scheduled orders from the pause date onwards are cancelled automatically. The subscription end date is extended when resumed to compensate for paused days.

**When to call:** When the user is going on vacation or wants to stop meals temporarily. Use `PUT /{subscription_id}/resume` to restart.

**Note:** Cannot pause if the subscription ends before tomorrow.

**Parameters:** `subscription_id` (path, string (uuid), required)

**Response model:** `PauseSubscriptionResponse` (see `app/schemas/`)


### `PUT /api/v1/user/subscription/{subscription_id}/resume` — Resume Paused Subscription

**Resume a paused subscription starting from tomorrow.**

The subscription end date is automatically extended by the number of days it was paused. Cancelled orders in the resumed window are reactivated and new orders are created for the extended period.

**When to call:** After `PUT /{subscription_id}/pause` when the user is ready to restart deliveries.

**Parameters:** `subscription_id` (path, string (uuid), required)

**Response model:** `ResumeSubscriptionResponse` (see `app/schemas/`)


## User Review

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/review` | List My Reviews |
| POST | `/api/v1/user/review` | Submit a Review |
| GET | `/api/v1/user/review/{review_id}` | Get Review Detail |
| PUT | `/api/v1/user/review/{review_id}` | Update a Review |
| DELETE | `/api/v1/user/review/{review_id}` | Delete a Review |
| GET | `/api/v1/user/review/vendor/{vendor_id}` | Get All Reviews for a Vendor |

### `GET /api/v1/user/review` — List My Reviews

**Fetch all reviews submitted by the logged-in user.**

Returns reviews in descending order of creation. Use `review_id` from this list to update or delete a specific review.

**When to call:** On the user's profile 'My Reviews' section.

**Response model:** `ReviewListResponse` (see `app/schemas/`)


### `POST /api/v1/user/review` — Submit a Review

**Rate and review a vendor after receiving a delivery.**

Required: `vendor_id` (the vendor's `provider_id`) and `vendor_rating` (1–5). Optional: `package_id`, `order_id`, `subscription_id`, `package_rating`, `review_text`, `review_date`.

Only one review per user per vendor per day is allowed (unique constraint). The vendor must exist — use `provider_id` from the package listing.

**When to call:** After an order is delivered (`status = delivered`). Show a 'Rate your meal' prompt on the order detail screen.

**Flow:** Order delivered → `POST /user/review` → `GET /user/review` to see your reviews

**Request body** (application/json): `vendor_id` (string (uuid), required); `vendor_rating` (integer, required); `package_rating` (integer (nullable), optional); `review_text` (string (nullable), optional); `package_id` (string (uuid) (nullable), optional); `order_id` (string (uuid) (nullable), optional); `subscription_id` (string (uuid) (nullable), optional); `review_date` (string (date) (nullable), optional)


### `GET /api/v1/user/review/{review_id}` — Get Review Detail

**Fetch a specific review by its ID.**

Use `review_id` from `GET /user/review`. Returns the full review including ratings, text, and associated vendor/package.

**When to call:** When the user taps on a review to view or edit it.

**Parameters:** `review_id` (path, string (uuid), required)

**Response model:** `ReviewResponse` (see `app/schemas/`)


### `PUT /api/v1/user/review/{review_id}` — Update a Review

**Edit the rating or text of an existing review.**

Send only the fields to update (`vendor_rating`, `package_rating`, `review_text`). Use `review_id` from `GET /user/review`.

**When to call:** When the user edits a review from 'My Reviews'.

**Parameters:** `review_id` (path, string (uuid), required)

**Request body** (application/json): `vendor_rating` (integer (nullable), optional); `package_rating` (integer (nullable), optional); `review_text` (string (nullable), optional)


### `DELETE /api/v1/user/review/{review_id}` — Delete a Review

**Soft-delete (hide) a review.**

The review is marked as not visible rather than permanently deleted. It will no longer appear in listings.

**When to call:** When the user taps 'Delete' on a review from 'My Reviews'.

**Parameters:** `review_id` (path, string (uuid), required)


### `GET /api/v1/user/review/vendor/{vendor_id}` — Get All Reviews for a Vendor

**Fetch all public reviews left for a specific vendor.**

Use `vendor_id` (the vendor's `provider_id` UUID). Display these on the vendor detail / package detail page to help users decide.

**When to call:** When rendering the vendor profile or package detail screen.

**Parameters:** `vendor_id` (path, string (uuid), required)

**Response model:** `ReviewListResponse` (see `app/schemas/`)


## User Complaint

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/complaint` | List My Complaints |
| POST | `/api/v1/user/complaint` | Raise a Complaint |
| GET | `/api/v1/user/complaint/{complaint_id}` | Get Complaint Detail |
| PUT | `/api/v1/user/complaint/{complaint_id}` | Update Complaint |
| DELETE | `/api/v1/user/complaint/{complaint_id}` | Withdraw Complaint |

### `GET /api/v1/user/complaint` — List My Complaints

**Fetch all complaints raised by the logged-in user.**

Returns complaint subject, status (`open`, `in_progress`, `resolved`, `closed`), and timestamps. Use `complaint_id` to view details or update.

**When to call:** On the 'My Complaints' / support history screen.

**Response model:** `ComplaintListResponse` (see `app/schemas/`)


### `POST /api/v1/user/complaint` — Raise a Complaint

**Submit a complaint about an order, delivery, or the platform.**

Provide `subject`, `description`, and optionally link an `order_id` or `subscription_id`. Returns the complaint ID and initial status (`open`).

**When to call:** When the user taps 'Report an Issue' on the order detail or support screen.

**Flow:** `POST /user/complaint` → `GET /user/complaint` to track status

**Request body** (application/json): `against` (ComplaintAgainst, required); `subject` (string, required); `description` (string, required); `vendor_id` (string (uuid) (nullable), optional); `order_id` (string (uuid) (nullable), optional); `subscription_id` (string (uuid) (nullable), optional); `evidence_urls` (array of string (nullable), optional)


### `GET /api/v1/user/complaint/{complaint_id}` — Get Complaint Detail

**Fetch full details of a specific complaint including admin response.**

Use `complaint_id` from `GET /user/complaint`.

**When to call:** When the user taps on a complaint to view its current status or resolution.

**Parameters:** `complaint_id` (path, string (uuid), required)

**Response model:** `ComplaintResponse` (see `app/schemas/`)


### `PUT /api/v1/user/complaint/{complaint_id}` — Update Complaint

**Edit the subject or description of an open complaint.**

Only complaints with status `open` can be updated. Use `complaint_id` from the complaints list.

**When to call:** When the user wants to add more details before an admin responds.

**Parameters:** `complaint_id` (path, string (uuid), required)

**Request body** (application/json): `subject` (string (nullable), optional); `description` (string (nullable), optional); `evidence_urls` (array of string (nullable), optional)


### `DELETE /api/v1/user/complaint/{complaint_id}` — Withdraw Complaint

**Withdraw (cancel) an open complaint.**

Use this if the user's issue was resolved informally or was raised by mistake. The complaint is marked as `closed`.

**When to call:** When the user taps 'Withdraw' on an open complaint.

**Parameters:** `complaint_id` (path, string (uuid), required)


## User Notification

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/user/notification` | List My Notifications |
| PUT | `/api/v1/user/notification/{notification_id}/read` | Mark Notification as Read |
| PUT | `/api/v1/user/notification/read-all` | Mark All Notifications as Read |

### `GET /api/v1/user/notification` — List My Notifications

**Fetch the logged-in user's notifications, newest first.**

Filter by `is_read` to show only unread or only read notifications. Response includes `unread_count` for a notification badge.

**When to call:** On the notifications screen, or on app open to show the unread badge.

**Parameters:** `is_read` (query, boolean (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)

**Response model:** `app__schemas__notification_schema__NotificationListResponse` (see `app/schemas/`)


### `PUT /api/v1/user/notification/{notification_id}/read` — Mark Notification as Read

**Mark a single notification as read.**

**When to call:** When the user taps/opens a notification.

**Parameters:** `notification_id` (path, string (uuid), required)

**Response model:** `MarkNotificationReadResponse` (see `app/schemas/`)


### `PUT /api/v1/user/notification/read-all` — Mark All Notifications as Read

**Mark every unread notification for this user as read.**

**When to call:** When the user taps 'Mark all as read' on the notifications screen.

**Response model:** `MarkNotificationReadResponse` (see `app/schemas/`)


## User Payment

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/user/payment/initiate` | Initiate Wallet Top-up Payment |
| POST | `/api/v1/user/payment/{payment_id}/confirm` | Confirm Wallet Top-up Payment |
| GET | `/api/v1/user/payment` | List My Payments |
| GET | `/api/v1/user/payment/{payment_id}` | Get Payment Detail |

### `POST /api/v1/user/payment/initiate` — Initiate Wallet Top-up Payment

**Start a wallet recharge via the payment gateway.**

Creates a `pending` payment and returns a `gateway_order_id` for the client to hand to the payment gateway SDK. No money moves yet.

**Flow:** `POST /user/payment/initiate` → pay via gateway SDK using `gateway_order_id` → `POST /user/payment/{payment_id}/confirm`

**Request body** (application/json): `amount` (number | string, required)

**Response model:** `InitiatePaymentResponse` (see `app/schemas/`)


### `POST /api/v1/user/payment/{payment_id}/confirm` — Confirm Wallet Top-up Payment

**Confirm a pending payment and credit the wallet.**

Call after the payment gateway SDK reports success, passing the `gateway_txn_id` it returned. Credits the wallet by the payment amount and marks the payment `completed`.

**When to call:** Immediately after the gateway SDK's success callback.

**Parameters:** `payment_id` (path, string (uuid), required)

**Request body** (application/json): `gateway_txn_id` (string, required)

**Response model:** `ConfirmPaymentResponse` (see `app/schemas/`)


### `GET /api/v1/user/payment` — List My Payments

**Fetch all payments made by the logged-in user.**

**When to call:** On the payment / billing history screen.

**Response model:** `PaymentListResponse` (see `app/schemas/`)


### `GET /api/v1/user/payment/{payment_id}` — Get Payment Detail

**Fetch full details of a specific payment.**

Use `payment_id` from `GET /user/payment`.

**Parameters:** `payment_id` (path, string (uuid), required)

**Response model:** `PaymentResponse` (see `app/schemas/`)

