# Admin API Reference

> Generated from the FastAPI OpenAPI spec (regenerate with `python scripts/gen_api_docs.py` if endpoints change). Base URL: `http://<host>:8000`; paths below are complete (they already include `/api/v1`).

Consumed by the **Admin panel** (web dashboard for operations: user/provider/delivery-boy management, content, payments).

**Auth:** unless stated otherwise in the endpoint description, endpoints require the role's JWT as `Authorization: Bearer <access_token>` (obtained from the login endpoint in the Auth section).

## Source file map

| Tag (Swagger group) | Endpoint file | Service file |
|---|---|---|
| Admin Auth | app/api/v1/endpoints/admin_auth.py | app/services/admin_auth_service.py |
| Admin Dashboard | app/api/v1/endpoints/admin_dashboard.py | app/services/admin_dashboard_service.py |
| Admin — Users | app/api/v1/endpoints/admin_users.py | app/services/admin_user_service.py |
| Admin — Providers | app/api/v1/endpoints/admin_providers.py | app/services/admin_provider_service.py |
| Admin — Delivery Boys | app/api/v1/endpoints/admin_delivery_boys.py | app/services/admin_delivery_boy_service.py |
| Admin — Packages | app/api/v1/endpoints/admin_packages.py | app/services/admin_content_service.py |
| Admin — Plans | app/api/v1/endpoints/admin_plans.py | app/services/admin_content_service.py |
| Admin — Complaints | app/api/v1/endpoints/admin_complaints.py | app/services/admin_complaint_service.py |
| Admin — Reviews | app/api/v1/endpoints/admin_reviews.py | app/services/admin_review_service.py |
| Admin — Orders | app/api/v1/endpoints/admin_orders.py | app/services/admin_order_service.py |
| Admin — Pincodes | app/api/v1/endpoints/admin_pincodes.py | app/services/pincode_service.py |
| Admin — Payments | app/api/v1/endpoints/admin_payments.py | app/services/admin_payment_service.py |

Repositories live in `app/repositories/`, request/response schemas in `app/schemas/`, DB models in `app/models/`. Routers are registered with prefixes and tags in `app/api/v1/api.py`.

## Admin Auth

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/admin/auth/login` | Admin Login |
| GET | `/api/v1/admin/auth/profile` | Get Admin Profile |
| PUT | `/api/v1/admin/auth/change-password` | Change Admin Password |
| POST | `/api/v1/admin/auth/logout` | Admin Logout |

### `POST /api/v1/admin/auth/login` — Admin Login

**Login for admin users using email and password.**

Returns a JWT `access_token`. Include this in all admin API calls as `Authorization: Bearer <token>`.

**Admin roles:** `super_admin` has full access; `moderator` has limited access.

**After login:** Use `GET /admin/profile` to verify role and permissions.

**Request body** (application/json): `email` (string, required); `password` (string, required)

**Response model:** `AdminLoginResponse` (see `app/schemas/`)


### `GET /api/v1/admin/auth/profile` — Get Admin Profile

**Fetch the logged-in admin's profile including role and permissions.**

**When to call:** On admin panel load to determine which sections the admin can access based on their role (`super_admin` or `moderator`).


### `PUT /api/v1/admin/auth/change-password` — Change Admin Password

**Change the password for the currently logged-in admin account.**

Send `current_password` and `new_password`. The session token remains valid after the change.

**Request body** (application/json): `current_password` (string, required); `new_password` (string, required)


### `POST /api/v1/admin/auth/logout` — Admin Logout

**Invalidate the current admin session.**

Call this when the admin logs out of the panel. The client should discard the stored token after this call.

**Response model:** `LogoutResponse` (see `app/schemas/`)


## Admin Dashboard

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/dashboard` | Admin Dashboard Overview |

### `GET /api/v1/admin/dashboard` — Admin Dashboard Overview

**Fetch high-level platform statistics for the admin dashboard.**

Returns key metrics including:
- Total users, providers, delivery boys
- Active subscriptions count
- Orders delivered today
- Revenue / wallet totals

**When to call:** On every admin panel load or dashboard screen. Refresh periodically to keep metrics current.


## Admin — Users

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/users` | List All Users |
| GET | `/api/v1/admin/users/{user_id}` | Get User Detail |
| PUT | `/api/v1/admin/users/{user_id}/status` | Update User Status |
| POST | `/api/v1/admin/users/{user_id}/wallet/adjust` | Manually Adjust User Wallet |
| PUT | `/api/v1/admin/users/subscriptions/{subscription_id}/cancel` | Admin Cancel Subscription |

### `GET /api/v1/admin/users` — List All Users

**Fetch a paginated list of all registered users.**

Filter by `status` (`active`, `suspended`) and/or search by name, phone, or email. Use `page` and `limit` for pagination (default: 20 per page).

**When to call:** On the admin user management screen.

**Parameters:** `status` (query, string (nullable), optional); `search` (query, string (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `GET /api/v1/admin/users/{user_id}` — Get User Detail

**Fetch full profile, subscription history, wallet balance, and order summary for a user.**

Use `user_id` (UUID) from the users list. Use this before taking any action on the user account.

**Parameters:** `user_id` (path, string (uuid), required)


### `PUT /api/v1/admin/users/{user_id}/status` — Update User Status

**Activate or suspend a user account.**

Set `status` to `active` or `suspended`. Suspended users cannot log in or place orders. Provide a `reason` for audit trail purposes.

**Requires:** `super_admin` role.

**Parameters:** `user_id` (path, string (uuid), required)

**Request body** (application/json): `status` (string, required); `reason` (string (nullable), optional)


### `POST /api/v1/admin/users/{user_id}/wallet/adjust` — Manually Adjust User Wallet

**Credit or debit a user's wallet balance manually.**

Use for refunds, compensation, or corrections. Send `amount` (positive for credit, use negative for debit), `type` (`credit`/`debit`), and `description` (reason for the adjustment — stored in transaction history).

**Requires:** Admin authentication. All adjustments are logged.

**Parameters:** `user_id` (path, string (uuid), required)

**Request body** (application/json): `amount` (number | string, required); `type` (string, required); `reason` (string, required); `description` (string (nullable), optional)


### `PUT /api/v1/admin/users/subscriptions/{subscription_id}/cancel` — Admin Cancel Subscription

**Force-cancel a user's subscription on their behalf.**

Use when the user is unable to cancel themselves, or for policy reasons. Provide an optional `reason` query parameter for the audit log.

**Requires:** Admin authentication.

**Parameters:** `subscription_id` (path, string (uuid), required); `reason` (query, string (nullable), optional)


## Admin — Providers

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/providers` | List All Providers |
| GET | `/api/v1/admin/providers/{provider_id}` | Get Provider Detail |
| PUT | `/api/v1/admin/providers/{provider_id}` | Update Provider Details |
| PUT | `/api/v1/admin/providers/{provider_id}/activate` | Activate Provider Account |
| PUT | `/api/v1/admin/providers/{provider_id}/deactivate` | Deactivate Provider Account |
| POST | `/api/v1/admin/providers/{provider_id}/wallet/adjust` | Manually Adjust Provider Earnings Wallet |
| PUT | `/api/v1/admin/providers/{provider_id}/accepting-orders` | Toggle Provider Order Acceptance |
| GET | `/api/v1/admin/providers/{provider_id}/unavailability` | List Provider Unavailability Dates |
| POST | `/api/v1/admin/providers/{provider_id}/unavailability` | Mark Provider as Unavailable on a Date |
| DELETE | `/api/v1/admin/providers/{provider_id}/unavailability/{unavailable_date}` | Remove Provider Unavailability Date |

### `GET /api/v1/admin/providers` — List All Providers

**Fetch a paginated list of all registered vendors/kitchens.**

Filter by `search` (business name or mobile), `pincode`, and/or `is_profile_completed`. Use this to monitor vendor onboarding and find providers needing attention.

**When to call:** On the admin vendor management screen.

**Parameters:** `search` (query, string (nullable), optional); `pincode` (query, integer (nullable), optional); `is_profile_completed` (query, boolean (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `GET /api/v1/admin/providers/{provider_id}` — Get Provider Detail

**Fetch full profile, packages, earnings, and subscription summary for a vendor.**

Use `provider_id` (UUID) from the providers list.

**Parameters:** `provider_id` (path, string (uuid), required)


### `PUT /api/v1/admin/providers/{provider_id}` — Update Provider Details

**Edit a provider's business name, address, pincode, or other profile fields.**

Use this for admin-side corrections when the provider cannot update themselves.

**Parameters:** `provider_id` (path, string (uuid), required)

**Request body** (application/json): `full_name` (string (nullable), optional); `business_name` (string (nullable), optional); `city` (string (nullable), optional); `area` (string (nullable), optional); `pincode` (integer (nullable), optional); `is_profile_completed` (boolean (nullable), optional)


### `PUT /api/v1/admin/providers/{provider_id}/activate` — Activate Provider Account

**Set a provider account to active, allowing them to receive orders.**

Use after verifying the provider's documents and profile. New providers must be activated before they appear in user package listings.

**Parameters:** `provider_id` (path, string (uuid), required)


### `PUT /api/v1/admin/providers/{provider_id}/deactivate` — Deactivate Provider Account

**Suspend a provider account, preventing them from appearing in user listings or receiving new orders.**

Existing active subscriptions are not automatically cancelled — handle those separately.

**Parameters:** `provider_id` (path, string (uuid), required)


### `POST /api/v1/admin/providers/{provider_id}/wallet/adjust` — Manually Adjust Provider Earnings Wallet

**Credit or debit a provider's earnings wallet manually.**

Use for corrections, penalties, or bonus payments. All adjustments are logged with the admin ID and description for auditing.

**Parameters:** `provider_id` (path, string (uuid), required)

**Request body** (application/json): `amount` (number | string, required); `type` (string, required); `reason` (string, required); `description` (string (nullable), optional)


### `PUT /api/v1/admin/providers/{provider_id}/accepting-orders` — Toggle Provider Order Acceptance

**Enable or disable a provider's ability to accept new orders.**

Pass `accepting=true` to enable or `accepting=false` to pause. This is separate from account activation — use when a provider temporarily cannot fulfill orders (e.g. equipment issues) without fully deactivating their account.

**Parameters:** `provider_id` (path, string (uuid), required); `accepting` (query, boolean, required)


### `GET /api/v1/admin/providers/{provider_id}/unavailability` — List Provider Unavailability Dates

**Fetch all dates when the provider has been marked as unavailable.**

On these dates no new orders are created and existing scheduled orders may be skipped. Use before marking new unavailability to avoid duplicates.

**Parameters:** `provider_id` (path, string (uuid), required)


### `POST /api/v1/admin/providers/{provider_id}/unavailability` — Mark Provider as Unavailable on a Date

**Block a specific date for a provider (e.g. public holiday, equipment maintenance).**

Orders scheduled for that date will be treated as skipped. Provide `unavailable_date` (YYYY-MM-DD) and an optional `reason`.

**Parameters:** `provider_id` (path, string (uuid), required)

**Request body** (application/json): `date` (string (date), required); `reason` (string (nullable), optional)


### `DELETE /api/v1/admin/providers/{provider_id}/unavailability/{unavailable_date}` — Remove Provider Unavailability Date

**Remove a previously set unavailability date for a provider.**

Use if the provider confirms they can fulfill orders on that date after all. Scheduled orders for that date may need to be manually reinstated.

**Parameters:** `provider_id` (path, string (uuid), required); `unavailable_date` (path, string (date), required)


## Admin — Delivery Boys

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/delivery-boys` | List All Delivery Boys |
| GET | `/api/v1/admin/delivery-boys/{delivery_boy_id}` | Get Delivery Boy Detail |
| PUT | `/api/v1/admin/delivery-boys/{delivery_boy_id}` | Update Delivery Boy Details |
| PUT | `/api/v1/admin/delivery-boys/{delivery_boy_id}/assign-provider` | Assign Delivery Boy to a Provider |

### `GET /api/v1/admin/delivery-boys` — List All Delivery Boys

**Fetch a paginated list of all registered delivery personnel.**

Filter by `search` (name or mobile), `is_active`, and/or `provider_id` to see delivery boys assigned to a specific vendor.

**When to call:** On the admin delivery management screen or when assigning a new delivery boy to a provider.

**Parameters:** `search` (query, string (nullable), optional); `is_active` (query, boolean (nullable), optional); `provider_id` (query, string (uuid) (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `GET /api/v1/admin/delivery-boys/{delivery_boy_id}` — Get Delivery Boy Detail

**Fetch full profile and delivery statistics for a specific delivery boy.**

Returns assigned provider, active status, and order completion summary. Use `delivery_boy_id` (UUID) from the delivery boys list.

**Parameters:** `delivery_boy_id` (path, string (uuid), required)


### `PUT /api/v1/admin/delivery-boys/{delivery_boy_id}` — Update Delivery Boy Details

**Edit a delivery boy's name, active status, or other profile fields.**

Use for admin-side corrections or to deactivate a delivery boy. To reassign to a different provider, use `PUT /{delivery_boy_id}/assign-provider` instead.

**Parameters:** `delivery_boy_id` (path, string (uuid), required)

**Request body** (application/json): `full_name` (string (nullable), optional); `vehicle_type` (string (nullable), optional); `vehicle_number` (string (nullable), optional); `assigned_provider_id` (string (uuid) (nullable), optional); `is_active` (boolean (nullable), optional)


### `PUT /api/v1/admin/delivery-boys/{delivery_boy_id}/assign-provider` — Assign Delivery Boy to a Provider

**Link a delivery boy to a specific vendor/provider.**

Pass `provider_id` as a query parameter. The delivery boy will then appear in that provider's delivery team and can be assigned to that provider's orders.

**When to call:** During onboarding of a new delivery boy, or when reassigning between providers.

**Parameters:** `delivery_boy_id` (path, string (uuid), required); `provider_id` (query, string (uuid), required)


## Admin — Packages

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/admin/packages` | Create Platform Package (Predefined) |
| GET | `/api/v1/admin/packages` | List All Packages (Admin View) |
| GET | `/api/v1/admin/packages/{package_id}` | Get Package Detail (Admin View) |
| PUT | `/api/v1/admin/packages/{package_id}` | Update Package (Admin) |
| DELETE | `/api/v1/admin/packages/{package_id}` | Delete Package (Admin) |

### `POST /api/v1/admin/packages` — Create Platform Package (Predefined)

**Create a platform-level predefined meal package that providers can adopt.**

Predefined packages serve as templates. Providers can select them via `POST /provider/packages/select` to offer under their own brand without creating from scratch.

**Requires:** `super_admin` role.

**Request body** (application/json): `category_id` (string (uuid), required); `package_name` (string, required); `short_description` (string (nullable), optional); `description` (string (nullable), optional); `meal_type` (string | array of string, required); `food_type` (string, required); `price` (number | string, required); `discounted_price` (number | string (nullable), optional); `is_subscription_available` (boolean, optional); `subscription_price` (number | string (nullable), optional); `items` (array of AdminPackageItemRequest, required)


### `GET /api/v1/admin/packages` — List All Packages (Admin View)

**Fetch all meal packages across all providers.**

Filter by `is_predefined`, `is_active`, `provider_id`, or `search` term. Use this to audit package content, moderate listings, or find packages needing review.

**When to call:** On the admin package management screen.

**Parameters:** `is_predefined` (query, boolean (nullable), optional); `is_active` (query, boolean (nullable), optional); `provider_id` (query, string (uuid) (nullable), optional); `search` (query, string (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `GET /api/v1/admin/packages/{package_id}` — Get Package Detail (Admin View)

**Fetch complete package details including items, images, and provider info.**

Use `package_id` from the packages list. Use before editing or deactivating a package.

**Parameters:** `package_id` (path, string (uuid), required)


### `PUT /api/v1/admin/packages/{package_id}` — Update Package (Admin)

**Edit a package's details or toggle `is_active` / `is_available` flags.**

Setting `is_active=false` hides the package from user listings immediately. Use this when a provider violates listing guidelines.

**Parameters:** `package_id` (path, string (uuid), required)

**Request body** (application/json): `package_name` (string (nullable), optional); `description` (string (nullable), optional); `price` (number | string (nullable), optional); `discounted_price` (number | string (nullable), optional); `is_active` (boolean (nullable), optional); `is_available` (boolean (nullable), optional)


### `DELETE /api/v1/admin/packages/{package_id}` — Delete Package (Admin)

**Permanently delete a meal package.**

Cannot delete packages with active subscriptions. Use `PUT /{package_id}` with `is_active=false` to hide it from users instead.

**Parameters:** `package_id` (path, string (uuid), required)


## Admin — Plans

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/admin/plans` | Create Subscription Plan |
| GET | `/api/v1/admin/plans` | List Subscription Plans |
| GET | `/api/v1/admin/plans/{plan_id}` | Get Plan Detail |
| PUT | `/api/v1/admin/plans/{plan_id}` | Update Subscription Plan |

### `POST /api/v1/admin/plans` — Create Subscription Plan

**Create a new subscription plan that users can choose from.**

Required: `meal_slot` (e.g. `lunch`, `all_slots`), `subscription_type` (e.g. `weekly`, `monthly`), `duration_days`, `discount_percent`, `free_skips`.

Users see active plans on `GET /user/subscription/plans`. Only active plans appear in the user-facing listing.

**Requires:** `super_admin` role.

**Request body** (application/json): `subscription_type` (string, required); `meal_slot` (string, required); `duration_days` (integer, required); `free_skips` (integer, optional); `discount_percent` (number | string, optional)


### `GET /api/v1/admin/plans` — List Subscription Plans

**Fetch all subscription plans — both active and inactive.**

Filter by `is_active` to see only published plans. Use this on the admin plan management screen.

**Note:** Users only see plans with `is_active=true` via `GET /user/subscription/plans`.

**Parameters:** `is_active` (query, boolean (nullable), optional)


### `GET /api/v1/admin/plans/{plan_id}` — Get Plan Detail

**Fetch full details of a single subscription plan.**

Use `plan_id` from the plans list to review or prepare an update.

**Parameters:** `plan_id` (path, string (uuid), required)


### `PUT /api/v1/admin/plans/{plan_id}` — Update Subscription Plan

**Edit an existing subscription plan's details or toggle its active status.**

Setting `is_active=false` hides the plan from users immediately — existing subscriptions using this plan are not affected.

**Parameters:** `plan_id` (path, string (uuid), required)

**Request body** (application/json): `free_skips` (integer (nullable), optional); `discount_percent` (number | string (nullable), optional); `duration_days` (integer (nullable), optional); `is_active` (boolean (nullable), optional)


## Admin — Complaints

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/complaints` | List All Complaints |
| GET | `/api/v1/admin/complaints/user/{complaint_id}` | Get User Complaint Detail |
| GET | `/api/v1/admin/complaints/provider/{complaint_id}` | Get Provider Complaint Detail |
| GET | `/api/v1/admin/complaints/delivery-boy/{complaint_id}` | Get Delivery Boy Complaint Detail |
| PUT | `/api/v1/admin/complaints/delivery-boy/{complaint_id}/resolve` | Resolve Delivery Boy Complaint |
| PUT | `/api/v1/admin/complaints/user/{complaint_id}/resolve` | Resolve User Complaint |
| PUT | `/api/v1/admin/complaints/provider/{complaint_id}/resolve` | Resolve Provider Complaint |

### `GET /api/v1/admin/complaints` — List All Complaints

**Fetch a paginated list of all complaints — from users, providers, and delivery boys.**

Filter by:
- `complaint_type`: `user`, `provider`, or `delivery_boy`
- `status`: `open`, `in_progress`, `resolved`, `closed`, `rejected`
- `against`: `platform`, `delivery_boy`, `provider`, `vendor`, or `package`

**When to call:** On the admin complaints management screen. Focus on `open` and `in_progress` complaints that need action.

**Parameters:** `complaint_type` (query, string (nullable), optional); `status` (query, string (nullable), optional); `against` (query, string (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `GET /api/v1/admin/complaints/user/{complaint_id}` — Get User Complaint Detail

**Fetch full details of a complaint raised by a user.**

Returns subject, description, linked order/subscription, status, and any prior admin responses. Use `complaint_id` from the complaints list.

**Parameters:** `complaint_id` (path, string (uuid), required)


### `GET /api/v1/admin/complaints/provider/{complaint_id}` — Get Provider Complaint Detail

**Fetch full details of a complaint raised by a provider.**

Returns the complaint target (platform or delivery boy), description, and status. Use `complaint_id` from the complaints list.

**Parameters:** `complaint_id` (path, string (uuid), required)


### `GET /api/v1/admin/complaints/delivery-boy/{complaint_id}` — Get Delivery Boy Complaint Detail

**Fetch full details of a complaint raised by a delivery boy.**

Returns the complaint target (platform or provider), description, and status. Use `complaint_id` from the complaints list.

**Parameters:** `complaint_id` (path, string (uuid), required)


### `PUT /api/v1/admin/complaints/delivery-boy/{complaint_id}/resolve` — Resolve Delivery Boy Complaint

**Update the status and add an admin response to a delivery boy complaint.**

Set `status` to `resolved`, `rejected`, or `closed` and provide a `resolution_note` that will be visible to the delivery boy.

**Parameters:** `complaint_id` (path, string (uuid), required)

**Request body** (application/json): `status` (string, required); `admin_notes` (string (nullable), optional); `resolution` (string (nullable), optional)


### `PUT /api/v1/admin/complaints/user/{complaint_id}/resolve` — Resolve User Complaint

**Update the status and add an admin response to a user complaint.**

Set `status` to `resolved`, `rejected`, or `closed` and provide a `resolution_note` that will be visible to the user.

**Flow:** View complaint → take action (refund, reassign, etc.) → resolve with a note

**Parameters:** `complaint_id` (path, string (uuid), required)

**Request body** (application/json): `status` (string, required); `admin_notes` (string (nullable), optional); `resolution` (string (nullable), optional)


### `PUT /api/v1/admin/complaints/provider/{complaint_id}/resolve` — Resolve Provider Complaint

**Update the status and add an admin response to a provider complaint.**

Set `status` to `resolved`, `rejected`, or `closed` and provide a `resolution_note` that will be visible to the provider.

**Parameters:** `complaint_id` (path, string (uuid), required)

**Request body** (application/json): `status` (string, required); `admin_notes` (string (nullable), optional); `resolution` (string (nullable), optional)


## Admin — Reviews

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/reviews` | List All Reviews |
| PUT | `/api/v1/admin/reviews/{review_id}/visibility` | Show or Hide a Review |
| DELETE | `/api/v1/admin/reviews/{review_id}` | Delete a Review |

### `GET /api/v1/admin/reviews` — List All Reviews

**Fetch a paginated list of all user reviews across the platform.**

Filter by:
- `vendor_id`: reviews for a specific provider
- `min_rating` / `max_rating`: filter by star rating (1–5)
- `is_visible`: `true` for visible reviews, `false` for hidden

**When to call:** On the admin content moderation screen to spot and hide inappropriate reviews.

**Parameters:** `vendor_id` (query, string (uuid) (nullable), optional); `min_rating` (query, integer (nullable), optional); `max_rating` (query, integer (nullable), optional); `is_visible` (query, boolean (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `PUT /api/v1/admin/reviews/{review_id}/visibility` — Show or Hide a Review

**Toggle the visibility of a review on the platform.**

Pass `is_visible=true` to show or `is_visible=false` to hide. Hidden reviews are not returned in user-facing review lists but remain in the database.

**When to call:** During content moderation when a review violates community guidelines.

**Parameters:** `review_id` (path, string (uuid), required); `is_visible` (query, boolean, required)


### `DELETE /api/v1/admin/reviews/{review_id}` — Delete a Review

**Permanently delete a review from the platform.**

Use only for reviews that violate policy and should be removed entirely. For temporary hiding, use `PUT /{review_id}/visibility` instead.

**Parameters:** `review_id` (path, string (uuid), required)


## Admin — Orders

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/orders/subscriptions` | List All Subscriptions (Admin) |
| GET | `/api/v1/admin/orders/subscription-orders` | List Subscription Orders (Admin) |
| PUT | `/api/v1/admin/orders/subscription-orders/{order_id}/assign-delivery-boy` | Admin: Assign Delivery Boy to Order |
| PUT | `/api/v1/admin/orders/subscription-orders/{order_id}/reassign-provider` | Admin: Reassign Subscription Order to Another Provider |
| PUT | `/api/v1/admin/orders/subscription-orders/{order_id}/status` | Admin: Force Update Subscription Order Status |
| GET | `/api/v1/admin/orders/extra-orders` | List Extra (One-Time) Orders (Admin) |
| PUT | `/api/v1/admin/orders/extra-orders/{order_id}/assign-delivery-boy` | Admin: Assign Delivery Boy to Extra Order |
| PUT | `/api/v1/admin/orders/extra-orders/{order_id}/reassign-provider` | Admin: Reassign Extra Order to Another Provider |
| PUT | `/api/v1/admin/orders/extra-orders/{order_id}/status` | Admin: Force Update Extra Order Status |

### `GET /api/v1/admin/orders/subscriptions` — List All Subscriptions (Admin)

**Fetch a paginated list of all subscriptions across the platform.**

Filter by `vendor_id`, `user_id`, and/or `status`. Use to monitor subscription health, spot cancelled subscriptions, and resolve disputes.

**When to call:** On the admin orders / subscriptions overview screen.

**Parameters:** `vendor_id` (query, string (uuid) (nullable), optional); `user_id` (query, string (uuid) (nullable), optional); `status` (query, string (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `GET /api/v1/admin/orders/subscription-orders` — List Subscription Orders (Admin)

**Fetch daily subscription orders across all vendors.**

Filter by `vendor_id`, `user_id`, `order_date` (YYYY-MM-DD), and/or `status`. Use for operations monitoring: track how many orders are in each status for today.

**When to call:** On the admin real-time order tracking screen.

**Parameters:** `vendor_id` (query, string (uuid) (nullable), optional); `user_id` (query, string (uuid) (nullable), optional); `order_date` (query, string (date) (nullable), optional); `status` (query, string (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `PUT /api/v1/admin/orders/subscription-orders/{order_id}/assign-delivery-boy` — Admin: Assign Delivery Boy to Order

**Manually assign or reassign a delivery boy to a subscription order.**

Use when the provider hasn't assigned one, or when reassignment is needed due to delivery issues. Send `delivery_boy_id` in the request body.

**Parameters:** `order_id` (path, string (uuid), required)

**Request body** (application/json): `delivery_boy_id` (string (uuid), required); `reason` (string (nullable), optional)


### `PUT /api/v1/admin/orders/subscription-orders/{order_id}/reassign-provider` — Admin: Reassign Subscription Order to Another Provider

**Move a subscription order to a different provider.**

Use in emergency situations when the original provider cannot fulfill the order (e.g. kitchen closure, quality issue). Send `new_vendor_id` in the request body.

**Parameters:** `order_id` (path, string (uuid), required)

**Request body** (application/json): `new_provider_id` (string (uuid), required); `reason` (string (nullable), optional)


### `PUT /api/v1/admin/orders/subscription-orders/{order_id}/status` — Admin: Force Update Subscription Order Status

**Override a subscription order's status to any value.**

Use only for dispute resolution or data correction. Normal status changes should go through the provider (`PUT /provider/orders/subscription-orders/{id}/status`) or delivery boy (`PUT /delivery/orders/{id}/pickup` or `/deliver`) endpoints instead.

**Requires:** `super_admin` role.

**Parameters:** `order_id` (path, string (uuid), required)

**Request body** (application/json): `status` (string, required); `reason` (string (nullable), optional)


### `GET /api/v1/admin/orders/extra-orders` — List Extra (One-Time) Orders (Admin)

**Fetch a paginated list of all one-time orders across the platform.**

Filter by `vendor_id`, `user_id`, `delivery_date`, and/or `status`. Use to monitor on-demand order fulfillment.

**Parameters:** `vendor_id` (query, string (uuid) (nullable), optional); `user_id` (query, string (uuid) (nullable), optional); `delivery_date` (query, string (date) (nullable), optional); `status` (query, string (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)


### `PUT /api/v1/admin/orders/extra-orders/{order_id}/assign-delivery-boy` — Admin: Assign Delivery Boy to Extra Order

**Manually assign or reassign a delivery boy to a one-time order.**

Use when the provider hasn't assigned one or reassignment is needed. Send `delivery_boy_id` in the request body.

**Parameters:** `order_id` (path, string (uuid), required)

**Request body** (application/json): `delivery_boy_id` (string (uuid), required); `reason` (string (nullable), optional)


### `PUT /api/v1/admin/orders/extra-orders/{order_id}/reassign-provider` — Admin: Reassign Extra Order to Another Provider

**Move a one-time order to a different provider.**

Use for emergency reassignments when the original provider cannot fulfill. Send `new_vendor_id` in the request body.

**Parameters:** `order_id` (path, string (uuid), required)

**Request body** (application/json): `new_provider_id` (string (uuid), required); `reason` (string (nullable), optional)


### `PUT /api/v1/admin/orders/extra-orders/{order_id}/status` — Admin: Force Update Extra Order Status

**Override a one-time order's status to any value.**

Use only for dispute resolution or data correction. Normal status changes should go through the provider endpoint.

**Requires:** `super_admin` role.

**Parameters:** `order_id` (path, string (uuid), required)

**Request body** (application/json): `status` (string, required); `reason` (string (nullable), optional)


## Admin — Pincodes

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/pincodes` | List Serviceable Pincodes |
| POST | `/api/v1/admin/pincodes` | Add Serviceable Pincode |
| PUT | `/api/v1/admin/pincodes/{pincode_id}` | Update Pincode |
| DELETE | `/api/v1/admin/pincodes/{pincode_id}` | Delete Pincode |

### `GET /api/v1/admin/pincodes` — List Serviceable Pincodes

**Fetch all pincodes where Mealoo is active.**

Filter by `is_active` and/or `city`. These pincodes are what `POST /location/verify-pincode` checks against.

**When to call:** On the admin service area management screen.

**Parameters:** `is_active` (query, boolean (nullable), optional); `city` (query, string (nullable), optional)


### `POST /api/v1/admin/pincodes` — Add Serviceable Pincode

**Add a new pincode to the list of delivery-serviceable areas.**

Required: `pincode`, `city`, `state`. Optional: `is_active` (defaults to true).

Once added and active, users in this area can browse meal packages from local providers.

**Request body** (application/json): `pincode` (integer, required); `city` (string, required); `state` (string, required)


### `PUT /api/v1/admin/pincodes/{pincode_id}` — Update Pincode

**Edit an existing pincode entry (city, state, or active status).**

Set `is_active=false` to temporarily disable delivery in that area without permanently removing it.

**Parameters:** `pincode_id` (path, integer, required)

**Request body** (application/json): `city` (string (nullable), optional); `state` (string (nullable), optional); `is_active` (boolean (nullable), optional)


### `DELETE /api/v1/admin/pincodes/{pincode_id}` — Delete Pincode

**Permanently remove a pincode from the serviceable areas list.**

Users in this pincode will no longer see packages. Consider using `PUT /{pincode_id}` with `is_active=false` to disable without deleting.

**Parameters:** `pincode_id` (path, integer, required)


## Admin — Payments

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/admin/payments` | List All Payments |
| GET | `/api/v1/admin/payments/{payment_id}` | Get Payment Detail |
| PUT | `/api/v1/admin/payments/{payment_id}/refund` | Refund a Payment |

### `GET /api/v1/admin/payments` — List All Payments

**Fetch a paginated list of all payments across the platform.**

Filter by `status` (`pending`, `completed`, `failed`, `refunded`) and/or `method` (`wallet`, `upi`, `card`, `netbanking`, `cash`).

**When to call:** On the admin payments / financial reconciliation screen.

**Parameters:** `status` (query, string (nullable), optional); `method` (query, string (nullable), optional); `page` (query, integer, optional); `limit` (query, integer, optional)

**Response model:** `PaymentListResponse` (see `app/schemas/`)


### `GET /api/v1/admin/payments/{payment_id}` — Get Payment Detail

**Fetch full details of a specific payment, including gateway response data.**

Use `payment_id` from the payments list.

**Parameters:** `payment_id` (path, string (uuid), required)

**Response model:** `PaymentResponse` (see `app/schemas/`)


### `PUT /api/v1/admin/payments/{payment_id}/refund` — Refund a Payment

**Refund a completed payment and debit the amount back out of the user's wallet.**

Optionally specify a partial `refund_amount`; defaults to the full payment amount. The wallet debit is clamped to the user's current balance if it's lower than the refund amount.

**Requires:** `super_admin` role.

**Parameters:** `payment_id` (path, string (uuid), required)

**Request body** (application/json): `refund_amount` (number | string (nullable), optional); `reason` (string (nullable), optional)

