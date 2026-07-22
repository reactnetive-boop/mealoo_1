# Delivery Boy API Reference

> Generated from the FastAPI OpenAPI spec (regenerate with `python scripts/gen_api_docs.py` if endpoints change). Base URL: `http://<host>:8000`; paths below are complete (they already include `/api/v1`).

Consumed by the **Delivery partner mobile app** (Expo/React Native project `Mealoo_D`, screens in `src/app/`):
`welcome`, `register`, `verify-otp`, `login`, `complete-profile`, `upload-documents`, `vehicle-details`, `payout-details`, `application-submitted`, `home`, `orders`, `order-detail`, `navigate-provider`, `pickup-confirmation`, `pickup-otp-verification`, `navigate-customer`, `delivery-confirmation`, `delivery-success`, `wallet`, `transaction-history`, `earnings`, `notifications`, `profile`, `settings`.

**Auth:** unless stated otherwise in the endpoint description, endpoints require the role's JWT as `Authorization: Bearer <access_token>` (obtained from the login endpoint in the Auth section).

## Source file map

| Tag (Swagger group) | Endpoint file | Service file |
|---|---|---|
| Delivery Boy Auth | app/api/v1/endpoints/delivery_auth.py | app/services/delivery_boy_auth_service.py |
| Delivery Boy | app/api/v1/endpoints/delivery_orders.py | app/services/delivery_boy_order_service.py |
| Delivery Boy Account | app/api/v1/endpoints/delivery_account.py | app/services/delivery_boy_account_service.py |
| Delivery Boy Complaint | app/api/v1/endpoints/delivery_complaint.py | app/services/delivery_boy_complaint_service.py |

Repositories live in `app/repositories/`, request/response schemas in `app/schemas/`, DB models in `app/models/`. Routers are registered with prefixes and tags in `app/api/v1/api.py`.

## Screen → API map (Mealoo_D app)

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


## Delivery Boy Auth

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/delivery/auth/register` | Delivery Boy Register – Step 1: Send OTP |
| POST | `/api/v1/delivery/auth/verify-otp` | Delivery Boy Register – Step 2: Verify OTP |
| POST | `/api/v1/delivery/auth/login` | Delivery Boy Login |
| POST | `/api/v1/delivery/auth/logout` | Delivery Boy Logout |

### `POST /api/v1/delivery/auth/register` — Delivery Boy Register – Step 1: Send OTP

**First step of delivery boy registration.**

Provide a mobile number and password. An OTP is sent to the mobile. The delivery boy account is pre-assigned to a provider by the admin. Call `/delivery/verify-otp` next with the received OTP.

**Flow:** `POST /delivery/register` → `POST /delivery/verify-otp` → `POST /delivery/login`

**Request body** (application/json): `mobile_number` (string, required); `password` (string, required)

**Response model:** `DeliveryBoyRegisterResponse` (see `app/schemas/`)


### `POST /api/v1/delivery/auth/verify-otp` — Delivery Boy Register – Step 2: Verify OTP

**Second step of delivery boy registration.**

Submit the OTP received during registration to activate the account. On success the account is active and the delivery boy can log in.

**Flow:** `POST /delivery/register` → `POST /delivery/verify-otp` → `POST /delivery/login`

**Request body** (application/json): `mobile_number` (string, required); `otp` (string, required)

**Response model:** `DeliveryBoyAuthResponse` (see `app/schemas/`)


### `POST /api/v1/delivery/auth/login` — Delivery Boy Login

**Login for delivery personnel using mobile number and password.**

Returns a JWT `access_token`. Include this in all delivery API calls as `Authorization: Bearer <token>`.

**After login:** Call `GET /delivery/profile` to load the delivery boy's details and `GET /delivery/orders` to see today's assigned deliveries.

**Request body** (application/json): `mobile_number` (string, required); `password` (string, required)

**Response model:** `DeliveryBoyAuthResponse` (see `app/schemas/`)


### `POST /api/v1/delivery/auth/logout` — Delivery Boy Logout

**Invalidate the current delivery boy session.**

Call this when the delivery boy logs out of the app. The client should discard the stored token after this call.

**Response model:** `LogoutResponse` (see `app/schemas/`)


## Delivery Boy

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/delivery/profile` | Get Delivery Boy Profile |
| PUT | `/api/v1/delivery/profile` | Update Delivery Boy Profile |
| GET | `/api/v1/delivery/orders` | List My Subscription Delivery Orders |
| GET | `/api/v1/delivery/orders/{order_id}` | Get Subscription Order Detail |
| PUT | `/api/v1/delivery/orders/{order_id}/pickup` | Pickup Subscription Order from Provider |
| PUT | `/api/v1/delivery/orders/{order_id}/deliver` | Mark Subscription Order as Delivered |
| GET | `/api/v1/delivery/extra-orders` | List My Extra (One-Time) Delivery Orders |
| GET | `/api/v1/delivery/extra-orders/{order_id}` | Get Extra Order Detail |
| PUT | `/api/v1/delivery/extra-orders/{order_id}/pickup` | Pickup Extra Order from Provider |
| PUT | `/api/v1/delivery/extra-orders/{order_id}/deliver` | Mark Extra Order as Delivered |

### `GET /api/v1/delivery/profile` — Get Delivery Boy Profile

**Fetch the logged-in delivery boy's profile.**

Returns name, mobile, assigned provider, and account status.

**When to call:** On app launch after login, or when navigating to the profile screen.


### `PUT /api/v1/delivery/profile` — Update Delivery Boy Profile

**Update the delivery boy's name or other profile details.**

Only the fields provided will be updated.

**Request body** (application/json): `full_name` (string (nullable), optional); `email` (string (nullable), optional); `date_of_birth` (string (date) (nullable), optional); `gender` (string (nullable), optional); `vehicle_type` (string (nullable), optional); `vehicle_number` (string (nullable), optional); `is_online` (boolean (nullable), optional)


### `GET /api/v1/delivery/orders` — List My Subscription Delivery Orders

**Fetch subscription orders assigned to this delivery boy.**

Defaults to today's orders. Filter by `order_date`, `meal_slot` (breakfast / lunch / dinner), and/or `status`.

**When to call:** When the delivery boy opens the app to see their daily delivery list. Refresh before each meal slot.

**Flow:** Login → `GET /delivery/orders` → tap order → `GET /delivery/orders/{id}` → `PUT /delivery/orders/{id}/pickup` → `PUT /delivery/orders/{id}/deliver`

**Parameters:** `order_date` (query, string (date) (nullable), optional); `meal_slot` (query, string (nullable), optional); `status` (query, string (nullable), optional)

**Response model:** `DeliverySubscriptionOrderListResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/orders/{order_id}` — Get Subscription Order Detail

**Fetch full details of a specific subscription order.**

Returns delivery address, customer name, package items, meal slot, OTP for delivery confirmation, and current status.

**When to call:** When the delivery boy taps on an order from the list to navigate or confirm.

**Parameters:** `order_id` (path, string, required)

**Response model:** `DeliverySubscriptionOrderDetailResponse` (see `app/schemas/`)


### `PUT /api/v1/delivery/orders/{order_id}/pickup` — Pickup Subscription Order from Provider

**Mark a subscription order as picked up from the vendor's kitchen.**

The provider must have set the order status to `out_for_delivery` first. Call this when the delivery boy picks up the food parcel.

**Flow:** Provider sets `out_for_delivery` → delivery boy calls `PUT /orders/{id}/pickup` → `PUT /orders/{id}/deliver`

**Parameters:** `order_id` (path, string, required)

**Request body** (application/json): `delivery_notes` (string (nullable), optional)

**Response model:** `OrderActionResponse` (see `app/schemas/`)


### `PUT /api/v1/delivery/orders/{order_id}/deliver` — Mark Subscription Order as Delivered

**Confirm that a subscription order has been delivered to the customer.**

The customer's OTP may be required for confirmation (check `GET /orders/{id}` for the OTP field). This marks the order `delivered` and triggers the provider earnings credit.

**When to call:** After handing the order to the customer at their door.

**Parameters:** `order_id` (path, string, required)

**Request body** (application/json): `otp` (string, required); `delivery_notes` (string (nullable), optional)

**Response model:** `OrderActionResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/extra-orders` — List My Extra (One-Time) Delivery Orders

**Fetch one-time orders assigned to this delivery boy.**

Filter by `delivery_date`, `meal_slot`, and/or `status`. These are separate from subscription orders and need to be delivered alongside them.

**When to call:** Same time as `GET /delivery/orders` — check both lists each morning.

**Parameters:** `delivery_date` (query, string (date) (nullable), optional); `meal_slot` (query, string (nullable), optional); `status` (query, string (nullable), optional)

**Response model:** `DeliveryExtraOrderListResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/extra-orders/{order_id}` — Get Extra Order Detail

**Fetch full details of a specific one-time delivery order.**

Returns delivery address, customer info, items, amount, and current status.

**When to call:** When the delivery boy taps on an extra order to navigate to the address.

**Parameters:** `order_id` (path, string, required)

**Response model:** `DeliveryExtraOrderDetailResponse` (see `app/schemas/`)


### `PUT /api/v1/delivery/extra-orders/{order_id}/pickup` — Pickup Extra Order from Provider

**Mark a one-time order as picked up from the vendor.**

Call this when collecting the food parcel from the kitchen for an extra order.

**Flow:** Provider marks `out_for_delivery` → `PUT /extra-orders/{id}/pickup` → `PUT /extra-orders/{id}/deliver`

**Parameters:** `order_id` (path, string, required)

**Request body** (application/json): `delivery_notes` (string (nullable), optional)

**Response model:** `OrderActionResponse` (see `app/schemas/`)


### `PUT /api/v1/delivery/extra-orders/{order_id}/deliver` — Mark Extra Order as Delivered

**Confirm that a one-time (extra) order has been delivered to the customer.**

Call this after handing the parcel to the customer at their delivery address.

**Parameters:** `order_id` (path, string, required)

**Request body** (application/json): `delivery_notes` (string (nullable), optional)

**Response model:** `OrderActionResponse` (see `app/schemas/`)


## Delivery Boy Account

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/delivery/documents` | List My Documents |
| POST | `/api/v1/delivery/documents` | Upload a Document |
| GET | `/api/v1/delivery/payout-details` | Get My Payout Details |
| PUT | `/api/v1/delivery/payout-details` | Save My Payout Details |
| GET | `/api/v1/delivery/wallet` | Get My Wallet |
| GET | `/api/v1/delivery/wallet/transactions` | List My Wallet Transactions |
| GET | `/api/v1/delivery/earnings` | Get My Earnings Summary |
| GET | `/api/v1/delivery/notifications` | List My Notifications |
| PUT | `/api/v1/delivery/notifications/read-all` | Mark All Notifications Read |
| PUT | `/api/v1/delivery/notifications/{notification_id}/read` | Mark a Notification Read |

### `GET /api/v1/delivery/documents` — List My Documents

**Fetch all KYC documents uploaded by this delivery boy.**

Each document has a `status`: `pending` (awaiting review), `verified`, or `rejected`.

**When to call:** On the Upload Documents screen to show what's already uploaded.

**Response model:** `DeliveryBoyDocumentListResponse` (see `app/schemas/`)


### `POST /api/v1/delivery/documents` — Upload a Document

**Upload or replace a KYC document.**

Send `multipart/form-data` with a `document_type` field (`aadhaar` | `pan` | `driving_license` | `vehicle_rc`) and the image as `file`. Re-uploading the same type replaces the previous file and resets status to `pending`.

**When to call:** From the Upload Documents onboarding step.

**Request body** (multipart/form-data): `document_type` (string, required); `file` (string, required)

**Response model:** `DeliveryBoyDocumentUploadResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/payout-details` — Get My Payout Details

**Fetch saved bank account / UPI payout details.**

`payout_details` is `null` until the delivery boy saves them once.

**When to call:** To pre-fill the Bank & UPI screen.

**Response model:** `GetPayoutDetailsResponse` (see `app/schemas/`)


### `PUT /api/v1/delivery/payout-details` — Save My Payout Details

**Create or update bank account / UPI details for payouts.**

Partial update: only the fields you send are changed. A delivery boy can save just a UPI ID, just bank details, or both.

**When to call:** From the Bank & UPI onboarding step or profile settings.

**Request body** (application/json): `account_holder_name` (string (nullable), optional); `account_number` (string (nullable), optional); `ifsc_code` (string (nullable), optional); `bank_name` (string (nullable), optional); `upi_id` (string (nullable), optional)

**Response model:** `UpdatePayoutDetailsResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/wallet` — Get My Wallet

**Fetch the delivery boy's wallet balance and lifetime totals.**

The wallet is credited automatically on every completed delivery.

**When to call:** On the Wallet screen.

**Response model:** `GetWalletResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/wallet/transactions` — List My Wallet Transactions

**Fetch wallet transaction history, newest first.**

Filter by `type` (`credit` | `debit`). Each credit references the delivered order via `reference_id`/`reference_type`.

**When to call:** On the Transaction History screen.

**Parameters:** `type` (query, string (nullable), optional); `limit` (query, integer, optional)

**Response model:** `app__schemas__delivery_boy_schema__WalletTransactionListResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/earnings` — Get My Earnings Summary

**Earnings dashboard numbers: today, last 7 days, and this calendar month.**

`deliveries` counts payout credits in the period; `earnings` sums them. Also returns the current wallet snapshot.

**When to call:** On the Earnings screen.

**Response model:** `EarningsSummaryResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/notifications` — List My Notifications

**Fetch notifications for this delivery boy, newest first.**

Created automatically when an order is assigned and when a payout is credited.

**When to call:** On the Notifications screen; poll or refresh on app focus.

**Parameters:** `limit` (query, integer, optional)

**Response model:** `app__schemas__delivery_boy_schema__NotificationListResponse` (see `app/schemas/`)


### `PUT /api/v1/delivery/notifications/read-all` — Mark All Notifications Read

**Mark every unread notification as read.**


### `PUT /api/v1/delivery/notifications/{notification_id}/read` — Mark a Notification Read

**Mark a single notification as read.**

**Parameters:** `notification_id` (path, string, required)


## Delivery Boy Complaint

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/delivery/complaint` | Raise a Delivery Boy Complaint |
| GET | `/api/v1/delivery/complaint` | List My Complaints |
| GET | `/api/v1/delivery/complaint/{complaint_id}` | Get Complaint Detail |
| PUT | `/api/v1/delivery/complaint/{complaint_id}` | Update Complaint |
| DELETE | `/api/v1/delivery/complaint/{complaint_id}` | Withdraw Complaint |

### `POST /api/v1/delivery/complaint` — Raise a Delivery Boy Complaint

**Submit a complaint against the platform or a provider.**

Set `against` to `platform` for app / payout issues, or `provider` for kitchen-related problems. Optionally link a `provider_id`.

**When to call:** When the delivery boy encounters a problem via the support section.

**Flow:** `POST /delivery/complaint` → `GET /delivery/complaint` to track status

**Request body** (application/json): `against` (DeliveryBoyComplaintAgainst, required); `subject` (string, required); `description` (string, required); `provider_id` (string (uuid) (nullable), optional); `order_id` (string (uuid) (nullable), optional); `order_type` (string (nullable), optional); `evidence_urls` (array of string (nullable), optional)


### `GET /api/v1/delivery/complaint` — List My Complaints

**Fetch all complaints raised by this delivery boy.**

Filter by `against` (`platform` or `provider`) and/or `status` (`open`, `in_progress`, `resolved`, `closed`, `rejected`).

**When to call:** On the delivery boy's support / complaint history screen.

**Parameters:** `against` (query, string (nullable), optional); `status` (query, string (nullable), optional)

**Response model:** `DeliveryBoyComplaintListResponse` (see `app/schemas/`)


### `GET /api/v1/delivery/complaint/{complaint_id}` — Get Complaint Detail

**Fetch full details and admin response for a specific complaint.**

Use `complaint_id` from `GET /delivery/complaint`.

**When to call:** When the delivery boy taps a complaint to see updates or resolution.

**Parameters:** `complaint_id` (path, string (uuid), required)

**Response model:** `DeliveryBoyComplaintResponse` (see `app/schemas/`)


### `PUT /api/v1/delivery/complaint/{complaint_id}` — Update Complaint

**Edit the subject or description of an open complaint.**

Only complaints with status `open` can be updated. Use `complaint_id` from the complaints list.

**Parameters:** `complaint_id` (path, string (uuid), required)

**Request body** (application/json): `subject` (string (nullable), optional); `description` (string (nullable), optional); `evidence_urls` (array of string (nullable), optional)


### `DELETE /api/v1/delivery/complaint/{complaint_id}` — Withdraw Complaint

**Withdraw (cancel) an open complaint.**

The complaint is marked as `closed`. Use this if the issue was resolved informally.

**Parameters:** `complaint_id` (path, string (uuid), required)

