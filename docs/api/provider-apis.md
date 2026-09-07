# Provider (Vendor / Kitchen) API Reference

> Generated from the FastAPI OpenAPI spec (regenerate with `python scripts/gen_api_docs.py` if endpoints change). Base URL: `http://<host>:8000`; paths below are complete (they already include `/api/v1`).

Consumed by the **Provider mobile app** (vendor/kitchen owners managing menus, packages, orders, wallet).

**Auth:** unless stated otherwise in the endpoint description, endpoints require the role's JWT as `Authorization: Bearer <access_token>` (obtained from the login endpoint in the Auth section).

## Source file map

| Tag (Swagger group) | Endpoint file | Service file |
|---|---|---|
| Provider Auth | app/api/v1/endpoints/auth.py | app/services/auth_service.py, app/services/otp_service.py |
| Provider | app/api/v1/endpoints/provider.py | app/services/provider_service.py |
| Provider Menu | app/api/v1/endpoints/menu.py, app/api/v1/endpoints/provider_selected_package_endpoint.py | app/services/menu_service.py, app/services/provider_selected_package_service.py |
| Provider Package Item | app/api/v1/endpoints/package_item.py | app/services/package_item_service.py |
| Provider Package Image | app/api/v1/endpoints/package_image.py | app/services/package_image_service.py |
| Provider Orders | app/api/v1/endpoints/provider_orders.py | app/services/provider_order_service.py |
| Provider Wallet | app/api/v1/endpoints/provider_wallet.py | app/services/provider_wallet_service.py |
| Provider Complaint | app/api/v1/endpoints/provider_complaint.py | app/services/provider_complaint_service.py |

Repositories live in `app/repositories/`, request/response schemas in `app/schemas/`, DB models in `app/models/`. Routers are registered with prefixes and tags in `app/api/v1/api.py`.

## Provider Auth

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/auth/generate-otp` | Provider Register – Step 1: Send OTP |
| POST | `/api/v1/auth/verify-otp` | Provider Register – Step 2: Verify OTP |
| POST | `/api/v1/auth/login` | Provider Login |
| POST | `/api/v1/auth/logout` | Provider Logout |

### `POST /api/v1/auth/generate-otp` — Provider Register – Step 1: Send OTP

**First step of provider (vendor/kitchen) registration.**

Provide a mobile number and password. An OTP is sent to the mobile number. Call `/provider/verify-otp` next with the same mobile and the received OTP.

**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login` → `PUT /provider/complete-profile`

**Request body** (application/json): `mobile_number` (string, required); `password` (string, required)


### `POST /api/v1/auth/verify-otp` — Provider Register – Step 2: Verify OTP

**Second step of provider registration.**

Submit the OTP received on the registered mobile number. On success the provider account is activated and can log in.

**Flow:** `POST /generate-otp` → `POST /verify-otp` → `POST /login`

**Request body** (application/json): `mobile_number` (string, required); `otp` (string, required)


### `POST /api/v1/auth/login` — Provider Login

**Login for providers (vendors/kitchens) using mobile number and password.**

Returns a JWT `access_token`. Include this in all provider API calls as `Authorization: Bearer <token>`.

**After first login:** Call `PUT /provider/complete-profile` to fill in business details before the provider can accept orders.

**Request body** (application/json): `mobile_number` (string, required); `password` (string, required)


### `POST /api/v1/auth/logout` — Provider Logout

**Invalidate the current provider session.**

Call this when the provider logs out of the app. The client should discard the stored token after this call.

**Response model:** `LogoutResponse` (see `app/schemas/`)


## Provider

| Method | Path | Summary |
|---|---|---|
| PUT | `/api/v1/provider/complete-profile` | Complete Provider Profile |
| GET | `/api/v1/provider/profile` | Get Provider Profile |
| PUT | `/api/v1/provider/profile/image` | Upload Provider Profile Image |
| PUT | `/api/v1/provider/address` | Update Provider Address |

### `PUT /api/v1/provider/complete-profile` — Complete Provider Profile

**Fill in business details after the provider's first login.**

Required fields: business name, FSSAI number, address, pincode, meal types offered. This must be completed before the provider can create packages or appear in user listings.

**When to call:** Immediately after the first `POST /provider/login`. Check `GET /provider/profile` to see if the profile is already complete.

**Request body** (application/json): `full_name` (string, required); `business_name` (string, required); `city` (string, required); `area` (string, required); `address` (string, required); `kitchen_type` (string, required); `pincode` (integer, required); `house_no` (string (nullable), optional); `landmark` (string (nullable), optional); `state` (string, required); `meal_service_type` (MealServiceType (nullable), optional)


### `GET /api/v1/provider/profile` — Get Provider Profile

**Fetch the logged-in provider's full profile.**

Returns business name, mobile, address, pincode, service areas, meal types, profile image, and account status.

**When to call:** On the provider dashboard home screen or when navigating to profile settings.

**Response model:** `ProviderProfileResponse` (see `app/schemas/`)


### `PUT /api/v1/provider/profile/image` — Upload Provider Profile Image

**Upload or replace the provider's business profile photo.**

Send the image as `multipart/form-data` with field name `file`. Returns the new image URL. This image is shown to users on the package listing screen.

**Request body** (multipart/form-data): `file` (string, required)

**Response model:** `app__schemas__provider_schema__UpdateProfileImageResponse` (see `app/schemas/`)


### `PUT /api/v1/provider/address` — Update Provider Address

**Update the provider's registered business address and pincode.**

The pincode determines which user delivery areas the provider appears in. Changes take effect immediately for new users browsing packages.

**Request body** (application/json): `provider_id` (string, required); `house_no` (string, required); `address` (string, required); `landmark` (string (nullable), optional); `city` (string, required); `state` (string, required); `pincode` (integer, required)


## Provider Menu

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/menu/categories` | List All Menu Categories |
| GET | `/api/v1/menu/categories/{category_id}` | Get Category Detail |
| POST | `/api/v1/menu/package` | Create a Meal Package |
| GET | `/api/v1/menu/get/{package_id}` | Get Package Detail (Provider View) |
| GET | `/api/v1/menu/list/{provider_id}` | List Provider's Packages |
| PUT | `/api/v1/menu/update/{package_id}` | Update a Meal Package |
| DELETE | `/api/v1/menu/delete/{package_id}` | Delete a Meal Package |
| POST | `/api/v1/provider-package/select` | Select a Package to Offer |
| PUT | `/api/v1/provider-package/capacity` | Set Daily Package Capacity |

### `GET /api/v1/menu/categories` — List All Menu Categories

**Fetch all available food categories (e.g. South Indian, North Indian, Biryani).**

Use this to populate the category picker when a provider is creating a new meal package. Each category has a `category_id` required in `POST /menu/package`.

**No authentication required.** Can also be used on the user-facing filter/browse screen.

**Response model:** `GetMenuCategoryListResponse` (see `app/schemas/`)


### `GET /api/v1/menu/categories/{category_id}` — Get Category Detail

**Fetch details of a single food category by its ID.**

Returns category name and description. Use `category_id` from `GET /menu/categories`.

**Parameters:** `category_id` (path, string (uuid), required)

**Response model:** `MenuCategoryResponse` (see `app/schemas/`)


### `POST /api/v1/menu/package` — Create a Meal Package

**Create a new meal package under the logged-in provider's account.**

Required: `category_id` (from `GET /menu/categories`), `package_name`, `price`, `meal_type` (veg/non-veg/egg), and `food_type`. Optional: `short_description`, `description`, `discounted_price`, `subscription_price`, `is_subscription_available`.

After creation, add items via `POST /menu/items` and images via `POST /menu/images`. Then make the package available to users with `POST /provider/packages/select`.

**Flow:** `GET /menu/categories` → `POST /menu/package` → add items → add images → select package

**Request body** (application/json): `category_id` (string, required); `package_name` (string, required); `short_description` (string (nullable), optional); `description` (string (nullable), optional); `meal_type` (string, required); `food_type` (string, required); `price` (number, required); `discounted_price` (number (nullable), optional); `is_subscription_available` (boolean, optional); `subscription_price` (number (nullable), optional); `items` (array of PackageItemRequest, required)

**Response model:** `MenuPackageResponse` (see `app/schemas/`)


### `GET /api/v1/menu/get/{package_id}` — Get Package Detail (Provider View)

**Fetch full details of a meal package including items and images.**

Use this on the provider's package management screen to review or edit a package. Use `package_id` from `GET /menu/list/{provider_id}`.

**Parameters:** `package_id` (path, string (uuid), required)

**Response model:** `GetMenuPackageResponse` (see `app/schemas/`)


### `GET /api/v1/menu/list/{provider_id}` — List Provider's Packages

**Fetch all meal packages created by a specific provider.**

Pass `is_predefined=true` to fetch only system-wide predefined packages (templates the provider can adopt). Leave it `false` (default) for the provider's own packages.

**When to call:** On the provider's 'Manage Packages' screen or when selecting packages to offer.

**Parameters:** `provider_id` (path, string, required); `is_predefined` (query, boolean, optional)


### `PUT /api/v1/menu/update/{package_id}` — Update a Meal Package

**Edit details of an existing meal package.**

Only the fields provided will be updated. Changes to price or availability take effect immediately for new orders (existing subscriptions are not affected).

**When to call:** On the 'Edit Package' screen. Use `package_id` from `GET /menu/list/{provider_id}`.

**Parameters:** `package_id` (path, string (uuid), required)

**Request body** (application/json): `package_name` (string (nullable), optional); `short_description` (string (nullable), optional); `description` (string (nullable), optional); `meal_type` (string (nullable), optional); `food_type` (string (nullable), optional); `price` (number (nullable), optional); `discounted_price` (number (nullable), optional); `is_subscription_available` (boolean (nullable), optional); `subscription_price` (number (nullable), optional)

**Response model:** `CommonResponse` (see `app/schemas/`)


### `DELETE /api/v1/menu/delete/{package_id}` — Delete a Meal Package

**Permanently delete a meal package.**

Cannot delete a package that has active subscriptions linked to it. Consider marking it as unavailable (`is_available=false`) instead to hide it from users without affecting existing subscribers.

**When to call:** On the provider's package management screen.

**Parameters:** `package_id` (path, string (uuid), required)

**Response model:** `CommonResponse` (see `app/schemas/`)


### `POST /api/v1/provider-package/select` — Select a Package to Offer

**Add a meal package to the provider's active offering.**

After creating a package, the provider must explicitly select it to make it visible to users in their area. Requires `provider_id` and `package_id`.

**When to call:** After `POST /menu/package` or when the provider wants to start offering an existing package.

**Flow:** `POST /menu/package` → `POST /provider/packages/select` → package appears in `GET /user/menu/packages`

**Request body** (application/json): `provider_id` (string (uuid), required); `package_id` (string (uuid), required); `daily_capacity` (integer (nullable), optional)


### `PUT /api/v1/provider-package/capacity` — Set Daily Package Capacity

**Set or update the maximum daily order limit for a provider-package pair.**

Use this to prevent over-subscription. For example, a kitchen can cap a package at 50 servings per day per meal slot.

Send `daily_capacity=null` to remove the limit entirely.

**Validation:** The system rejects a new capacity that is lower than the current number of active subscriptions already consuming that package.

**When to call:** During package setup or when the provider needs to limit orders due to kitchen capacity changes.

**Request body** (application/json): `provider_id` (string (uuid), required); `package_id` (string (uuid), required); `daily_capacity` (integer (nullable), optional)

**Response model:** `UpdateCapacityResponse` (see `app/schemas/`)


## Provider Package Item

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/package/item/add` | Add Item to Package |
| PUT | `/api/v1/package/item/update/{item_id}` | Update Package Item |
| DELETE | `/api/v1/package/item/delete/{item_id}` | Delete Package Item |

### `POST /api/v1/package/item/add` — Add Item to Package

**Add a food item to a meal package's item list.**

Requires `package_id`, `item_name`, and `item_order` (display position). Optional: `quantity` (e.g. '2 pieces', '1 bowl'). Items are shown to users on the package detail screen.

**When to call:** After `POST /menu/package` to define what is included in the meal. Add all items before making the package available to users.

**Request body** (application/json): `package_id` (string (uuid), required); `item_name` (string, required); `quantity` (string (nullable), optional); `item_order` (integer (nullable), optional)


### `PUT /api/v1/package/item/update/{item_id}` — Update Package Item

**Edit the name, quantity, or display order of an existing package item.**

Use `item_id` from `GET /menu/get/{package_id}`. Changes are reflected immediately in the user-facing package detail view.

**Parameters:** `item_id` (path, string, required)

**Request body** (application/json): `item_name` (string (nullable), optional); `quantity` (string (nullable), optional); `item_order` (integer (nullable), optional)


### `DELETE /api/v1/package/item/delete/{item_id}` — Delete Package Item

**Remove a food item from a meal package.**

Use `item_id` from `GET /menu/get/{package_id}`. Existing subscriptions are not affected; the item simply stops appearing in the package listing.

**Parameters:** `item_id` (path, string, required)


## Provider Package Image

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/package/image/upload` | Upload Package Image |
| DELETE | `/api/v1/package/image/delete/{image_id}` | Delete Package Image |
| PUT | `/api/v1/package/image/set-primary/{image_id}` | Set Primary Package Image |

### `POST /api/v1/package/image/upload` — Upload Package Image

**Upload a photo for a meal package.**

Pass `package_id` as a query parameter and the image file as `multipart/form-data`. Multiple images can be uploaded per package. The first image uploaded automatically becomes the primary image.

**When to call:** After creating a package with `POST /menu/package`. Use `PUT /menu/images/set-primary/{image_id}` to change which image is shown first in listings.

**Parameters:** `package_id` (query, string (uuid), required)

**Request body** (multipart/form-data): `file` (string, required)


### `DELETE /api/v1/package/image/delete/{image_id}` — Delete Package Image

**Remove a specific image from a meal package.**

Use `image_id` returned from the upload or from `GET /menu/get/{package_id}`. If the deleted image was the primary image, set another image as primary with `PUT /menu/images/set-primary/{image_id}`.

**Parameters:** `image_id` (path, string (uuid), required)


### `PUT /api/v1/package/image/set-primary/{image_id}` — Set Primary Package Image

**Set a specific image as the primary/cover image for a package.**

The primary image is the one displayed on package cards in the user-facing listing. Only one image can be primary at a time — setting a new one automatically unsets the previous.

Use `image_id` from `GET /menu/get/{package_id}`.

**Parameters:** `image_id` (path, string (uuid), required)


## Provider Orders

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/provider/orders/subscriptions` | List Customer Subscriptions |
| GET | `/api/v1/provider/orders/subscriptions/{subscription_id}` | Get Subscription Detail |
| GET | `/api/v1/provider/orders/subscription-orders` | List Daily Subscription Orders |
| PUT | `/api/v1/provider/orders/subscription-orders/{order_id}/status` | Update Subscription Order Status |
| GET | `/api/v1/provider/orders/extra` | List One-Time (Extra) Orders |
| PUT | `/api/v1/provider/orders/extra/{order_id}/status` | Update Extra Order Status |
| PUT | `/api/v1/provider/orders/subscription-orders/{order_id}/assign-delivery-boy` | Assign Delivery Boy to Subscription Order |
| PUT | `/api/v1/provider/orders/extra/{order_id}/assign-delivery-boy` | Assign Delivery Boy to Extra Order |
| GET | `/api/v1/provider/orders/food-summary` | Daily Food Preparation Summary |

### `GET /api/v1/provider/orders/subscriptions` — List Customer Subscriptions

**Fetch all subscriptions where customers have chosen this provider's packages.**

Filter by `status` (`active`, `paused`, `cancelled`, `expired`). Each entry shows the customer, packages, meal slot, and date range.

**When to call:** On the provider dashboard to see the current subscriber base.

**Parameters:** `status` (query, string (nullable), optional)

**Response model:** `ProviderSubscriptionListResponse` (see `app/schemas/`)


### `GET /api/v1/provider/orders/subscriptions/{subscription_id}` — Get Subscription Detail

**Fetch full details of a single customer subscription.**

Returns customer info, packages subscribed, daily order schedule, meal slot, and financial summary.

**When to call:** When the provider taps on a subscription from the list.

**Parameters:** `subscription_id` (path, string, required)

**Response model:** `ProviderSubscriptionDetailResponse` (see `app/schemas/`)


### `GET /api/v1/provider/orders/subscription-orders` — List Daily Subscription Orders

**Fetch the list of subscription-based orders for a specific date.**

Defaults to today. Filter by `order_date` (YYYY-MM-DD) and/or `status`. Each order includes the customer's delivery address, meal slot, and current status.

**When to call:** Every morning when the provider prepares meals. Use alongside `GET /provider/orders/food-summary` to know how much food to prepare.

**Parameters:** `order_date` (query, string (date) (nullable), optional); `status` (query, string (nullable), optional)

**Response model:** `SubscriptionOrderListResponse` (see `app/schemas/`)


### `PUT /api/v1/provider/orders/subscription-orders/{order_id}/status` — Update Subscription Order Status

**Move a subscription order through its lifecycle.**

Valid status transitions:
- `scheduled` → `preparing` (provider starts cooking)
- `preparing` → `out_for_delivery` (handed to delivery boy)
- `out_for_delivery` → `delivered` (confirmed delivered)

**When to call:** As the kitchen processes each order. Assign a delivery boy first with `PUT /subscription-orders/{id}/assign-delivery-boy`.

**Parameters:** `order_id` (path, string, required)

**Request body** (application/json): `status` (string, required)

**Response model:** `UpdateOrderStatusResponse` (see `app/schemas/`)


### `GET /api/v1/provider/orders/extra` — List One-Time (Extra) Orders

**Fetch one-time orders placed by users (not part of a subscription).**

Filter by `delivery_date` and/or `status`. These are on-demand orders that need to be fulfilled alongside subscription orders.

**When to call:** On the provider's order management screen for same-day extra orders.

**Parameters:** `delivery_date` (query, string (date) (nullable), optional); `status` (query, string (nullable), optional)

**Response model:** `ProviderExtraOrderListResponse` (see `app/schemas/`)


### `PUT /api/v1/provider/orders/extra/{order_id}/status` — Update Extra Order Status

**Move a one-time (extra) order through its lifecycle.**

Valid status transitions: `pending` → `confirmed` → `preparing` → `out_for_delivery` → `delivered`.

Confirm the order first (`confirmed`) before preparing. Assign a delivery boy before marking `out_for_delivery`.

**Parameters:** `order_id` (path, string, required)

**Request body** (application/json): `status` (string, required)

**Response model:** `UpdateOrderStatusResponse` (see `app/schemas/`)


### `PUT /api/v1/provider/orders/subscription-orders/{order_id}/assign-delivery-boy` — Assign Delivery Boy to Subscription Order

**Assign a delivery boy to a subscription order before dispatching.**

Pass the `delivery_boy_id` (UUID). The delivery boy must belong to this provider. After assignment, update the order status to `out_for_delivery`.

**Flow:** `preparing` → assign delivery boy → `out_for_delivery`

**Parameters:** `order_id` (path, string, required)

**Request body** (application/json): `delivery_boy_id` (string (uuid), required)


### `PUT /api/v1/provider/orders/extra/{order_id}/assign-delivery-boy` — Assign Delivery Boy to Extra Order

**Assign a delivery boy to a one-time (extra) order before dispatching.**

Pass the `delivery_boy_id` (UUID). After assignment, update status to `out_for_delivery`.

**Flow:** `confirmed` / `preparing` → assign delivery boy → `out_for_delivery`

**Parameters:** `order_id` (path, string, required)

**Request body** (application/json): `delivery_boy_id` (string (uuid), required)


### `GET /api/v1/provider/orders/food-summary` — Daily Food Preparation Summary

**Calculate how much food to prepare for a given date and meal slot.**

Returns a breakdown per package: total quantity needed across all active subscription and extra orders for that day. Defaults to today.

**When to call:** Every morning before the kitchen starts cooking, or the night before for next-day planning.

**Tip:** Filter by `meal_slot` (breakfast / lunch / dinner) to get slot-specific quantities.

**Parameters:** `summary_date` (query, string (date), optional); `meal_slot` (query, string (nullable), optional)

**Response model:** `DailyFoodSummaryResponse` (see `app/schemas/`)


## Provider Wallet

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/provider/wallet` | Get Provider Wallet Balance |
| GET | `/api/v1/provider/wallet/transactions` | Provider Wallet Transaction History |
| POST | `/api/v1/provider/wallet/withdraw` | Request Earnings Withdrawal |

### `GET /api/v1/provider/wallet` — Get Provider Wallet Balance

**Fetch the provider's earnings wallet balance.**

Shows total earned, total withdrawn, and current available balance. Earnings are credited automatically as orders are delivered.

**When to call:** On the provider's earnings/wallet dashboard screen.

**Response model:** `ProviderWalletDetailsResponse` (see `app/schemas/`)


### `GET /api/v1/provider/wallet/transactions` — Provider Wallet Transaction History

**Fetch credit and debit transactions for the provider's earnings wallet.**

Filter by `type`: `credit` (deliveries paid out) or `debit` (withdrawals). Use this to show the earnings history on the wallet screen.

**When to call:** When the provider navigates to 'Earnings History'.

**Parameters:** `type` (query, string (nullable), optional)

**Response model:** `ProviderWalletTransactionListResponse` (see `app/schemas/`)


### `POST /api/v1/provider/wallet/withdraw` — Request Earnings Withdrawal

**Request a withdrawal of available earnings to a bank account.**

Send the `amount` to withdraw. The system validates sufficient available balance. Withdrawals are processed by the admin team.

**When to call:** When the provider wants to transfer earnings to their bank account. Check balance first with `GET /provider/wallet`.

**Request body** (application/json): `amount` (number | string, required); `description` (string (nullable), optional)

**Response model:** `WithdrawalResponse` (see `app/schemas/`)


## Provider Complaint

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/provider/complaint` | Raise a Provider Complaint |
| GET | `/api/v1/provider/complaint` | List My Complaints |
| GET | `/api/v1/provider/complaint/{complaint_id}` | Get Complaint Detail |
| PUT | `/api/v1/provider/complaint/{complaint_id}` | Update Complaint |
| DELETE | `/api/v1/provider/complaint/{complaint_id}` | Withdraw Complaint |

### `POST /api/v1/provider/complaint` — Raise a Provider Complaint

**Submit a complaint against the platform or a delivery boy.**

Set `against` to `platform` for billing / feature issues, or `delivery_boy` for delivery-related problems. Optionally link a `delivery_boy_id`.

**When to call:** When the provider encounters a problem via the support section.

**Flow:** `POST /provider/complaint` → `GET /provider/complaint` to track status

**Request body** (application/json): `against` (ProviderComplaintAgainst, required); `subject` (string, required); `description` (string, required); `delivery_boy_id` (string (uuid) (nullable), optional); `order_id` (string (uuid) (nullable), optional); `order_type` (string (nullable), optional); `evidence_urls` (array of string (nullable), optional)


### `GET /api/v1/provider/complaint` — List My Complaints

**Fetch all complaints raised by this provider.**

Filter by `against` (`platform` or `delivery_boy`) and/or `status` (`open`, `in_progress`, `resolved`, `closed`, `rejected`).

**When to call:** On the provider's support / complaint history screen.

**Parameters:** `against` (query, string (nullable), optional); `status` (query, string (nullable), optional)

**Response model:** `ProviderComplaintListResponse` (see `app/schemas/`)


### `GET /api/v1/provider/complaint/{complaint_id}` — Get Complaint Detail

**Fetch full details and admin response for a specific complaint.**

Use `complaint_id` from `GET /provider/complaint`.

**When to call:** When the provider taps a complaint to see updates or resolution.

**Parameters:** `complaint_id` (path, string (uuid), required)

**Response model:** `ProviderComplaintResponse` (see `app/schemas/`)


### `PUT /api/v1/provider/complaint/{complaint_id}` — Update Complaint

**Edit the subject or description of an open complaint.**

Only complaints with status `open` can be updated. Use `complaint_id` from the complaints list.

**Parameters:** `complaint_id` (path, string (uuid), required)

**Request body** (application/json): `subject` (string (nullable), optional); `description` (string (nullable), optional); `evidence_urls` (array of string (nullable), optional)


### `DELETE /api/v1/provider/complaint/{complaint_id}` — Withdraw Complaint

**Withdraw (cancel) an open complaint.**

The complaint is marked as `closed`. Use this if the issue was resolved informally.

**Parameters:** `complaint_id` (path, string (uuid), required)

