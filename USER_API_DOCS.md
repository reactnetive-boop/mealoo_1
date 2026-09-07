# Mealoo Backend — User API Documentation

> **Base URL:** `http://<your-server>/api/v1`
> **Authentication:** All protected endpoints require an HTTP Bearer token in the request header:
> ```
> Authorization: Bearer <jwt_token>
> ```
> The JWT token is returned after a successful Login or OTP Verify call.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [User Profile](#2-user-profile)
3. [Address Management](#3-address-management)
4. [Location & Pincode](#4-location--pincode)
5. [Browse Packages (Menu)](#5-browse-packages-menu)
6. [Subscription Plans](#6-subscription-plans)
7. [Subscriptions](#7-subscriptions)
8. [Extra (One-Time) Orders](#8-extra-one-time-orders)
9. [Wallet](#9-wallet)
10. [Reviews](#10-reviews)
11. [Complaints](#11-complaints)
12. [Quick Reference Table](#12-quick-reference-table)

---

## 1. Authentication

> **Prefix:** `/user/auth`
> **Auth Required:** No

### 1.1 Generate OTP

Start registration or password-reset flow. Sends OTP to phone or email.

- **Method:** `POST`
- **URL:** `/api/v1/user/auth/generate-otp`
- **Auth:** None

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `phone` | string | Conditional | 10–15 digit mobile number. Either `phone` or `email` must be provided. |
| `email` | string | Conditional | Max 255 chars. Either `phone` or `email` must be provided. |
| `password` | string | Yes | 8–64 characters |

**Sample Request:**
```json
{
  "phone": "9876543210",
  "password": "MyPass@123"
}
```

**Sample Response:**
```json
{
  "success": true,
  "message": "OTP sent successfully"
}
```

---

### 1.2 Verify OTP

Verify the OTP received on phone/email. Returns JWT token on success (completes registration).

- **Method:** `POST`
- **URL:** `/api/v1/user/auth/verify-otp`
- **Auth:** None

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `phone` | string | Conditional | Either `phone` or `email` must be provided |
| `email` | string | Conditional | Either `phone` or `email` must be provided |
| `otp` | string | Yes | 6-digit OTP code |

**Sample Request:**
```json
{
  "phone": "9876543210",
  "otp": "482910"
}
```

**Sample Response:**
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "phone": "9876543210",
    "email": null,
    "full_name": null,
    "is_profile_completed": false,
    "status": "active"
  }
}
```

---

### 1.3 Login

Login with existing credentials (phone/email + password).

- **Method:** `POST`
- **URL:** `/api/v1/user/auth/login`
- **Auth:** None

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `phone` | string | Conditional | Either `phone` or `email` must be provided |
| `email` | string | Conditional | Either `phone` or `email` must be provided |
| `password` | string | Yes | 8–64 characters |

**Sample Request:**
```json
{
  "phone": "9876543210",
  "password": "MyPass@123"
}
```

**Sample Response:**
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "phone": "9876543210",
    "email": "user@example.com",
    "full_name": "Rahul Sharma",
    "is_profile_completed": true,
    "status": "active"
  }
}
```

---

## 2. User Profile

> **Prefix:** `/user`
> **Auth Required:** Yes (Bearer Token)

### 2.1 Get Profile

Fetch the currently logged-in user's profile.

- **Method:** `GET`
- **URL:** `/api/v1/user/profile`
- **Auth:** Yes

**Response Fields:**

| Field | Type | Notes |
|-------|------|-------|
| `user_id` | UUID | Unique user identifier |
| `phone` | string \| null | Registered phone number |
| `email` | string \| null | Registered email |
| `full_name` | string \| null | Full name |
| `gender` | string \| null | `male` \| `female` \| `other` \| `prefer_not_to_say` |
| `date_of_birth` | date \| null | Format: `YYYY-MM-DD` |
| `avatar_url` | string \| null | Profile picture URL |
| `is_profile_completed` | boolean | Whether profile is fully set up |
| `status` | string | `active` \| `inactive` \| `suspended` \| `deleted` |
| `referral_code` | string \| null | User's referral code |
| `created_at` | datetime \| null | Account creation timestamp |

**Sample Response:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "phone": "9876543210",
  "email": "user@example.com",
  "full_name": "Rahul Sharma",
  "gender": "male",
  "date_of_birth": "1995-06-15",
  "avatar_url": "/uploads/avatars/abc.jpg",
  "is_profile_completed": true,
  "status": "active",
  "referral_code": "RAHUL123",
  "created_at": "2025-01-10T10:30:00Z"
}
```

---

### 2.2 Update Profile

Update the user's profile information. Send only the fields you want to change.

- **Method:** `PUT`
- **URL:** `/api/v1/user/profile`
- **Auth:** Yes

**Request Body (all fields optional):**

| Field | Type | Notes |
|-------|------|-------|
| `full_name` | string | Max 100 characters |
| `gender` | string | `male` \| `female` \| `other` \| `prefer_not_to_say` |
| `date_of_birth` | date | Format: `YYYY-MM-DD` |
| `avatar_url` | string | URL of profile image |
| `email` | string | Max 255 characters |

**Sample Request:**
```json
{
  "full_name": "Rahul Sharma",
  "gender": "male",
  "date_of_birth": "1995-06-15",
  "email": "rahul@example.com"
}
```

**Sample Response:** Returns the updated profile object (same structure as Get Profile).

---

### 2.3 Update Profile Image

Upload a new profile picture using multipart form upload.

- **Method:** `PUT`
- **URL:** `/api/v1/user/profile/image`
- **Auth:** Yes
- **Content-Type:** `multipart/form-data`

**Form Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | File (binary) | Yes | Image file (jpg, png, etc.) |

**Sample Response:**
```json
{
  "success": true,
  "message": "Profile image updated successfully",
  "avatar_url": "/uploads/avatars/user_550e8400.jpg"
}
```

---

## 3. Address Management

> **Prefix:** `/user`
> **Auth Required:** Yes (Bearer Token)

### 3.1 Add Address

Add a new delivery address for the user.

- **Method:** `POST`
- **URL:** `/api/v1/user/address`
- **Auth:** Yes

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `label` | string | No | e.g., `Home`, `Work`, `Other` (max 50 chars) |
| `address_line1` | string | Yes | House/flat number, street name |
| `address_line2` | string | No | Apartment/unit/building details |
| `landmark` | string | No | Nearby landmark |
| `city` | string | Yes | City name |
| `state` | string | Yes | State name |
| `pin_code` | string | Yes | Postal/PIN code (max 10 chars) |
| `country` | string | No | Country code, default: `"IN"` (max 6 chars) |
| `latitude` | decimal | No | GPS latitude (-90 to 90) |
| `longitude` | decimal | No | GPS longitude (-180 to 180) |
| `is_default` | boolean | No | Set as default address (default: `false`) |

**Sample Request:**
```json
{
  "label": "Home",
  "address_line1": "Flat 402, Sunrise Towers",
  "address_line2": "Near City Mall",
  "landmark": "Opposite State Bank",
  "city": "Pune",
  "state": "Maharashtra",
  "pin_code": "411001",
  "country": "IN",
  "latitude": 18.5204,
  "longitude": 73.8567,
  "is_default": true
}
```

**Sample Response:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "label": "Home",
  "address_line1": "Flat 402, Sunrise Towers",
  "address_line2": "Near City Mall",
  "landmark": "Opposite State Bank",
  "city": "Pune",
  "state": "Maharashtra",
  "pin_code": "411001",
  "country": "IN",
  "latitude": "18.520400",
  "longitude": "73.856700",
  "is_default": true,
  "is_active": true,
  "created_at": "2025-06-21T10:00:00Z",
  "updated_at": "2025-06-21T10:00:00Z"
}
```

---

### 3.2 Get All Addresses

Fetch all saved delivery addresses for the logged-in user.

- **Method:** `GET`
- **URL:** `/api/v1/user/address`
- **Auth:** Yes

**Sample Response:**
```json
{
  "success": true,
  "total": 2,
  "addresses": [
    {
      "id": "a1b2c3d4-...",
      "label": "Home",
      "address_line1": "Flat 402, Sunrise Towers",
      "city": "Pune",
      "state": "Maharashtra",
      "pin_code": "411001",
      "is_default": true,
      "is_active": true
    },
    {
      "id": "b2c3d4e5-...",
      "label": "Work",
      "address_line1": "Plot 5, IT Park",
      "city": "Pune",
      "state": "Maharashtra",
      "pin_code": "411014",
      "is_default": false,
      "is_active": true
    }
  ]
}
```

---

### 3.3 Get Single Address

Fetch details of one specific saved address.

- **Method:** `GET`
- **URL:** `/api/v1/user/address/{address_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `address_id` | UUID | Yes | Address identifier |

**Sample Response:** Returns a single address object (same structure as individual address in Get All Addresses, but with all fields).

---

### 3.4 Update Address

Update an existing delivery address. Send only fields you want to change.

- **Method:** `PUT`
- **URL:** `/api/v1/user/address/{address_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `address_id` | UUID | Yes |

**Request Body (all optional):**

| Field | Type | Notes |
|-------|------|-------|
| `label` | string | Max 50 chars |
| `address_line1` | string | Primary address line |
| `address_line2` | string | Secondary address line |
| `landmark` | string | Nearby landmark |
| `city` | string | City name |
| `state` | string | State name |
| `pin_code` | string | Postal/PIN code (max 10 chars) |
| `country` | string | Country code (max 6 chars) |
| `latitude` | decimal | GPS latitude |
| `longitude` | decimal | GPS longitude |
| `is_default` | boolean | Set as default |

**Sample Response:** Returns the updated address object.

---

### 3.5 Delete Address

Remove a saved delivery address.

- **Method:** `DELETE`
- **URL:** `/api/v1/user/address/{address_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `address_id` | UUID | Yes |

**Sample Response:**
```json
{
  "success": true,
  "message": "Address deleted successfully"
}
```

---

## 4. Location & Pincode

> **Auth Required:** No

### 4.1 Verify Pincode

Check if a given PIN code is serviceable before placing an order.

- **Method:** `POST`
- **URL:** `/api/v1/location/verify-pincode`
- **Auth:** None

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `pincode` | integer | Yes | Postal/PIN code to verify |
| `provider_id` | string | No | Vendor ID for location-specific check |
| `house_no` | string | No | House number |
| `address` | string | No | Full address |
| `landmark` | string | No | Nearby landmark |
| `city` | string | No | City name |
| `state` | string | No | State name |

**Sample Request:**
```json
{
  "pincode": 411001
}
```

**Sample Response:**
```json
{
  "success": true,
  "serviceable": true,
  "city": "Pune",
  "state": "Maharashtra",
  "message": "This pincode is serviceable"
}
```

---

## 5. Browse Packages (Menu)

> **Prefix:** `/user/menu`
> **Auth Required:** Yes (Bearer Token)

### 5.1 List Available Packages

Browse tiffin/meal packages available in a service area. Filter by category and pincode.

- **Method:** `GET`
- **URL:** `/api/v1/user/menu/packages`
- **Auth:** Yes

**Query Parameters:**

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `category_ids` | array of UUID | Yes | One or more category IDs (e.g., `?category_ids=uuid1&category_ids=uuid2`) |
| `pin_code` | integer | Yes | Service area pincode |

**Sample URL:** `/api/v1/user/menu/packages?category_ids=abc-uuid&pin_code=411001`

**Response Fields (per package):**

| Field | Type | Notes |
|-------|------|-------|
| `package_id` | UUID | Package identifier |
| `category_id` | UUID | Category this package belongs to |
| `provider_id` | UUID | Vendor/tiffin provider ID |
| `package_name` | string | Name of the meal package |
| `short_description` | string \| null | Brief description |
| `meal_type` | string \| null | e.g., `veg`, `non-veg` |
| `food_type` | string \| null | Cuisine type |
| `price` | decimal | Regular/one-time price |
| `discounted_price` | decimal \| null | Discounted price (if any) |
| `is_subscription_available` | boolean | Can be subscribed to |
| `subscription_price` | decimal \| null | Subscription price per day |
| `is_available` | boolean | Currently available to order |
| `primary_image` | string \| null | Package image URL |

**Sample Response:**
```json
{
  "success": true,
  "total": 3,
  "packages": [
    {
      "package_id": "pkg-uuid-1",
      "category_id": "cat-uuid-1",
      "provider_id": "vendor-uuid-1",
      "package_name": "Veg Lunch Thali",
      "short_description": "3 roti, 1 sabzi, dal, rice, pickle",
      "meal_type": "veg",
      "food_type": "north_indian",
      "price": "80.00",
      "discounted_price": null,
      "is_subscription_available": true,
      "subscription_price": "70.00",
      "is_available": true,
      "primary_image": "/uploads/packages/thali1.jpg"
    }
  ]
}
```

---

### 5.2 Get Package Details

Get complete details of a specific package including all food items and images.

- **Method:** `GET`
- **URL:** `/api/v1/user/menu/packages/{package_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `package_id` | UUID | Yes |

**Sample Response:**
```json
{
  "package_id": "pkg-uuid-1",
  "category_id": "cat-uuid-1",
  "provider_id": "vendor-uuid-1",
  "package_name": "Veg Lunch Thali",
  "short_description": "3 roti, 1 sabzi, dal, rice, pickle",
  "description": "A wholesome North Indian lunch with 3 rotis, seasonal sabzi, dal tadka, steamed rice, pickle, and papad.",
  "meal_type": "veg",
  "food_type": "north_indian",
  "price": "80.00",
  "discounted_price": null,
  "is_subscription_available": true,
  "subscription_price": "70.00",
  "is_available": true,
  "items": [
    { "item_id": "item-uuid-1", "item_name": "Roti", "quantity": 3, "item_order": 1 },
    { "item_id": "item-uuid-2", "item_name": "Dal Tadka", "quantity": 1, "item_order": 2 }
  ],
  "images": [
    { "image_id": "img-uuid-1", "image_url": "/uploads/packages/thali1.jpg", "is_primary": true, "display_order": 1 }
  ]
}
```

---

## 6. Subscription Plans

> **Prefix:** `/user/subscription`
> **Auth Required:** Yes (Bearer Token)

### 6.1 Get Plan Options

Fetch available meal slot types and subscription duration types (for building filter UI).

- **Method:** `GET`
- **URL:** `/api/v1/user/subscription/plans/options`
- **Auth:** Yes

**Sample Response:**
```json
{
  "meal_slots": ["breakfast", "lunch", "dinner", "breakfast_lunch", "lunch_dinner", "breakfast_dinner", "all_slots"],
  "subscription_types": ["weekly", "monthly", "quarterly", "half_yearly", "annually", "custom"]
}
```

---

### 6.2 List Subscription Plans

Browse available subscription plans, optionally filtered by meal slot or duration type.

- **Method:** `GET`
- **URL:** `/api/v1/user/subscription/plans`
- **Auth:** Yes

**Query Parameters:**

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `meal_slot` | string | No | Filter: `breakfast` \| `lunch` \| `dinner` \| `breakfast_lunch` \| `lunch_dinner` \| `breakfast_dinner` \| `all_slots` |
| `subscription_type` | string | No | Filter: `weekly` \| `monthly` \| `quarterly` \| `half_yearly` \| `annually` \| `custom` |

**Response Fields (per plan):**

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Plan identifier |
| `subscription_type` | string | Duration type |
| `meal_slot` | string | Meal slot covered |
| `duration_days` | integer | Number of days the plan covers |
| `free_skips` | integer | Number of days user can skip for free |
| `discount_percent` | decimal | Discount percentage offered |

**Sample Response:**
```json
{
  "success": true,
  "total": 4,
  "plans": [
    {
      "id": "plan-uuid-1",
      "subscription_type": "monthly",
      "meal_slot": "lunch",
      "duration_days": 30,
      "free_skips": 4,
      "discount_percent": "10.00"
    }
  ]
}
```

---

## 7. Subscriptions

> **Prefix:** `/user/subscription`
> **Auth Required:** Yes (Bearer Token)

### 7.1 Create Subscription

Subscribe to a meal plan (starts recurring daily meal delivery).

- **Method:** `POST`
- **URL:** `/api/v1/user/subscription`
- **Auth:** Yes

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `vendor_id` | UUID | Yes | The tiffin provider's ID |
| `plan_id` | UUID | Yes | Subscription plan ID (from List Plans) |
| `address_id` | UUID | Yes | Delivery address ID |
| `start_date` | date | Yes | Subscription start date (format: `YYYY-MM-DD`) |
| `items` | array | Yes | At least 1 item required |
| `items[].package_id` | UUID | Yes | Package to subscribe to |
| `items[].quantity` | integer | Yes | Quantity per delivery (1–5) |

**Sample Request:**
```json
{
  "vendor_id": "vendor-uuid-1",
  "plan_id": "plan-uuid-1",
  "address_id": "addr-uuid-1",
  "start_date": "2025-07-01",
  "items": [
    {
      "package_id": "pkg-uuid-1",
      "quantity": 1
    }
  ]
}
```

**Sample Response:**
```json
{
  "success": true,
  "message": "Subscription created successfully",
  "subscription_id": "sub-uuid-1",
  "total_amount": "2400.00",
  "discount_amount": "240.00",
  "final_amount": "2160.00",
  "wallet_balance": "840.00"
}
```

---

### 7.2 Get My Subscriptions

Fetch all subscriptions of the logged-in user.

- **Method:** `GET`
- **URL:** `/api/v1/user/subscription`
- **Auth:** Yes

**Sample Response:**
```json
{
  "success": true,
  "total": 1,
  "subscriptions": [
    {
      "id": "sub-uuid-1",
      "vendor_id": "vendor-uuid-1",
      "status": "active",
      "meal_slot": "lunch",
      "subscription_type": "monthly",
      "start_date": "2025-07-01",
      "end_date": "2025-07-30",
      "free_skips_total": 4,
      "free_skips_used": 0,
      "final_amount": "2160.00"
    }
  ]
}
```

---

### 7.3 Get Subscription Details

Fetch full details of a specific subscription.

- **Method:** `GET`
- **URL:** `/api/v1/user/subscription/{subscription_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `subscription_id` | UUID | Yes |

**Response Fields:**

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Subscription ID |
| `user_id` | UUID | User ID |
| `vendor_id` | UUID | Provider ID |
| `plan_id` | UUID | Plan ID |
| `user_address_id` | UUID | Delivery address ID |
| `status` | string | `active` \| `paused` \| `cancelled` \| `expired` \| `pending` |
| `meal_slot` | string | `breakfast` \| `lunch` \| `dinner` |
| `subscription_type` | string | `weekly` \| `monthly` \| `half_yearly` \| `yearly` |
| `start_date` | date | Start date |
| `end_date` | date | End date |
| `free_skips_total` | integer | Total allowed free skips |
| `free_skips_used` | integer | Free skips consumed |
| `total_amount` | decimal | Original total |
| `discount_amount` | decimal | Discount applied |
| `final_amount` | decimal | Amount after discount |
| `pause_start_date` | date \| null | Date paused (if paused) |
| `total_days_paused` | integer | Total number of days paused |
| `notes` | string \| null | User notes |
| `cancelled_at` | datetime \| null | Cancellation timestamp |
| `cancel_reason` | string \| null | Cancellation reason |
| `created_at` | datetime \| null | Created timestamp |
| `packages` | array | Subscribed packages (id, package_id, quantity, unit_price) |

---

### 7.4 Cancel Subscription

Cancel an active subscription.

- **Method:** `PUT`
- **URL:** `/api/v1/user/subscription/{subscription_id}/cancel`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `subscription_id` | UUID | Yes |

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `cancel_reason` | string | No | Reason for cancellation (max 500 chars) |

**Sample Request:**
```json
{
  "cancel_reason": "Travelling out of city"
}
```

**Sample Response:**
```json
{
  "success": true,
  "message": "Subscription cancelled successfully"
}
```

---

### 7.5 Pause Subscription

Pause an active subscription temporarily.

- **Method:** `PUT`
- **URL:** `/api/v1/user/subscription/{subscription_id}/pause`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `subscription_id` | UUID | Yes |

**Request Body:** None

**Sample Response:**
```json
{
  "success": true,
  "message": "Subscription paused successfully",
  "pause_start_date": "2025-06-21"
}
```

---

### 7.6 Resume Subscription

Resume a paused subscription. The end date is extended for the paused duration.

- **Method:** `PUT`
- **URL:** `/api/v1/user/subscription/{subscription_id}/resume`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `subscription_id` | UUID | Yes |

**Request Body:** None

**Sample Response:**
```json
{
  "success": true,
  "message": "Subscription resumed successfully",
  "resume_date": "2025-07-05",
  "new_end_date": "2025-08-04",
  "days_paused": 5,
  "new_orders_created": 5
}
```

---

### 7.7 List Subscribed Packages

Get a list of packages the user has an active subscription for.

- **Method:** `GET`
- **URL:** `/api/v1/user/subscription/packages`
- **Auth:** Yes

**Sample Response:** Returns a list of subscribed packages in `UserPackageListResponse` format (same structure as Browse Packages response).

---

## 8. Extra (One-Time) Orders

> **Prefix:** `/user/order`
> **Auth Required:** Yes (Bearer Token)

These are one-off orders placed outside a subscription (e.g., extra meal for a day).

### 8.1 Place Extra Order

Place one or more one-time meal orders.

- **Method:** `POST`
- **URL:** `/api/v1/user/order/extra`
- **Auth:** Yes

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `vendor_id` | UUID | Yes | Tiffin provider ID |
| `address_id` | UUID | Yes | Delivery address ID |
| `delivery_date` | date | Yes | Date to deliver (format: `YYYY-MM-DD`) |
| `meal_slot` | string | Yes | `breakfast` \| `lunch` \| `dinner` |
| `items` | array | Yes | At least 1 item required |
| `items[].package_id` | UUID | Yes | Package ID to order |
| `items[].quantity` | integer | Yes | Quantity (1–5) |

**Sample Request:**
```json
{
  "vendor_id": "vendor-uuid-1",
  "address_id": "addr-uuid-1",
  "delivery_date": "2025-06-25",
  "meal_slot": "lunch",
  "items": [
    {
      "package_id": "pkg-uuid-1",
      "quantity": 2
    }
  ]
}
```

**Sample Response:**
```json
{
  "success": true,
  "message": "Order placed successfully",
  "total_amount": "160.00",
  "wallet_balance_after": "840.00",
  "orders": [
    {
      "id": "order-uuid-1",
      "package_id": "pkg-uuid-1",
      "quantity": 2,
      "total_price": "160.00",
      "delivery_date": "2025-06-25",
      "meal_slot": "lunch",
      "status": "confirmed"
    }
  ]
}
```

---

### 8.2 Get Extra Orders List

Get history of all one-time (extra) orders placed by the user.

- **Method:** `GET`
- **URL:** `/api/v1/user/order/extra`
- **Auth:** Yes

**Sample Response:**
```json
{
  "success": true,
  "total": 5,
  "orders": [
    {
      "id": "order-uuid-1",
      "user_id": "user-uuid-1",
      "vendor_id": "vendor-uuid-1",
      "address_id": "addr-uuid-1",
      "package_id": "pkg-uuid-1",
      "quantity": 2,
      "unit_price": "80.00",
      "total_price": "160.00",
      "delivery_date": "2025-06-25",
      "meal_slot": "lunch",
      "status": "confirmed",
      "created_at": "2025-06-21T09:00:00Z"
    }
  ]
}
```

---

### 8.3 Get Extra Order Details

Get full details of a specific one-time order.

- **Method:** `GET`
- **URL:** `/api/v1/user/order/extra/{order_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `order_id` | UUID | Yes |

**Response Fields:**

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Order ID |
| `user_id` | UUID | User ID |
| `vendor_id` | UUID | Vendor ID |
| `address_id` | UUID | Delivery address ID |
| `package_id` | UUID | Ordered package ID |
| `quantity` | integer | Quantity ordered |
| `unit_price` | decimal | Price per unit |
| `total_price` | decimal | Total order amount |
| `delivery_date` | date | Delivery date |
| `meal_slot` | string | Meal slot |
| `status` | string | Order status |
| `created_at` | datetime \| null | Order creation time |

---

## 9. Wallet

> **Prefix:** `/user/wallet`
> **Auth Required:** Yes (Bearer Token)

### 9.1 Get Wallet Details

Fetch current wallet balance and recent transactions.

- **Method:** `GET`
- **URL:** `/api/v1/user/wallet`
- **Auth:** Yes

**Sample Response:**
```json
{
  "success": true,
  "wallet": {
    "id": "wallet-uuid-1",
    "user_id": "user-uuid-1",
    "balance": "1000.00",
    "created_at": "2025-01-10T10:00:00Z",
    "updated_at": "2025-06-21T08:00:00Z"
  },
  "transactions": [
    {
      "id": "txn-uuid-1",
      "type": "debit",
      "reason": "order_payment",
      "amount": "160.00",
      "balance_before": "1160.00",
      "balance_after": "1000.00",
      "description": "Extra order on 2025-06-21",
      "created_at": "2025-06-21T08:00:00Z"
    }
  ]
}
```

---

### 9.2 Get Transaction History

Fetch complete list of all wallet transactions.

- **Method:** `GET`
- **URL:** `/api/v1/user/wallet/transactions`
- **Auth:** Yes

**Response Fields (per transaction):**

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Transaction ID |
| `type` | string | `credit` \| `debit` \| `refund` |
| `reason` | string | Reason for transaction (e.g., `order_payment`, `recharge`, `subscription`) |
| `amount` | decimal | Transaction amount |
| `balance_before` | decimal | Wallet balance before this transaction |
| `balance_after` | decimal | Wallet balance after this transaction |
| `description` | string \| null | Additional notes |
| `created_at` | datetime \| null | Transaction timestamp |

---

### 9.3 Recharge Wallet

Add money to the user's wallet (typically called after payment gateway confirmation).

- **Method:** `POST`
- **URL:** `/api/v1/user/wallet/recharge`
- **Auth:** Yes

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `amount` | decimal | Yes | Amount to add (must be positive) |
| `description` | string | No | Note for this recharge (max 255 chars) |

**Sample Request:**
```json
{
  "amount": 500.00,
  "description": "Wallet top-up via UPI"
}
```

**Sample Response:**
```json
{
  "success": true,
  "message": "Wallet recharged successfully",
  "balance_before": "500.00",
  "amount_added": "500.00",
  "balance_after": "1000.00"
}
```

---

## 10. Reviews

> **Prefix:** `/user/review`
> **Auth Required:** Yes (Bearer Token)

### 10.1 Add Review

Post a review for a vendor or package after an order/subscription.

- **Method:** `POST`
- **URL:** `/api/v1/user/review`
- **Auth:** Yes

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `vendor_id` | UUID | Yes | Vendor to review |
| `vendor_rating` | integer | Yes | Rating 1–5 |
| `package_rating` | integer | No | Package-specific rating 1–5 |
| `review_text` | string | No | Review text (max 1000 chars) |
| `package_id` | UUID | No | Related package |
| `order_id` | UUID | No | Related order |
| `subscription_id` | UUID | No | Related subscription |
| `review_date` | date | No | Date of review (format: `YYYY-MM-DD`) |

**Sample Request:**
```json
{
  "vendor_id": "vendor-uuid-1",
  "vendor_rating": 5,
  "package_rating": 4,
  "review_text": "Great food, delivered on time. Portions are generous!",
  "order_id": "order-uuid-1"
}
```

**Sample Response:** Returns the created review object.

---

### 10.2 Get My Reviews

Fetch all reviews submitted by the logged-in user.

- **Method:** `GET`
- **URL:** `/api/v1/user/review`
- **Auth:** Yes

**Sample Response:**
```json
{
  "success": true,
  "total": 2,
  "reviews": [
    {
      "id": "review-uuid-1",
      "vendor_id": "vendor-uuid-1",
      "vendor_rating": 5,
      "review_text": "Great food!",
      "is_visible": true,
      "created_at": "2025-06-20T18:00:00Z"
    }
  ]
}
```

---

### 10.3 Get Review Details

Fetch a specific review.

- **Method:** `GET`
- **URL:** `/api/v1/user/review/{review_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `review_id` | UUID | Yes |

---

### 10.4 Update Review

Edit an existing review (only rating and text can be updated).

- **Method:** `PUT`
- **URL:** `/api/v1/user/review/{review_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `review_id` | UUID | Yes |

**Request Body (all optional):**

| Field | Type | Notes |
|-------|------|-------|
| `vendor_rating` | integer | Updated vendor rating (1–5) |
| `package_rating` | integer | Updated package rating (1–5) |
| `review_text` | string | Updated review text (max 1000 chars) |

---

### 10.5 Delete Review

Remove a review you submitted.

- **Method:** `DELETE`
- **URL:** `/api/v1/user/review/{review_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `review_id` | UUID | Yes |

**Sample Response:**
```json
{
  "success": true,
  "message": "Review deleted successfully"
}
```

---

### 10.6 Get Vendor Reviews

Fetch all public reviews for a specific vendor.

- **Method:** `GET`
- **URL:** `/api/v1/user/review/vendor/{vendor_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `vendor_id` | UUID | Yes |

**Sample Response:**
```json
{
  "success": true,
  "total": 15,
  "reviews": [
    {
      "id": "review-uuid-1",
      "user_id": "user-uuid-1",
      "vendor_rating": 5,
      "review_text": "Best tiffin service!",
      "is_visible": true,
      "created_at": "2025-06-18T19:00:00Z"
    }
  ]
}
```

---

## 11. Complaints

> **Prefix:** `/user/complaint`
> **Auth Required:** Yes (Bearer Token)

### 11.1 Raise a Complaint

File a complaint against a vendor, delivery, or platform.

- **Method:** `POST`
- **URL:** `/api/v1/user/complaint`
- **Auth:** Yes

**Request Body:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `against` | string | Yes | `vendor` \| `platform` \| `delivery` \| `package` |
| `subject` | string | Yes | Short subject (max 255 chars) |
| `description` | string | Yes | Detailed description (10–2000 chars) |
| `vendor_id` | UUID | No | Vendor ID (required if `against` is `vendor`) |
| `order_id` | UUID | No | Related order ID |
| `subscription_id` | UUID | No | Related subscription ID |
| `evidence_urls` | array of string | No | Image or document URLs as proof |

**Sample Request:**
```json
{
  "against": "vendor",
  "subject": "Food delivered late and cold",
  "description": "Lunch was supposed to arrive by 1 PM but arrived at 3 PM and the food was cold. This has happened 3 times this week.",
  "vendor_id": "vendor-uuid-1",
  "order_id": "order-uuid-1"
}
```

**Sample Response:** Returns the created complaint object.

---

### 11.2 Get My Complaints

Fetch all complaints filed by the logged-in user.

- **Method:** `GET`
- **URL:** `/api/v1/user/complaint`
- **Auth:** Yes

**Sample Response:**
```json
{
  "success": true,
  "total": 1,
  "complaints": [
    {
      "id": "complaint-uuid-1",
      "against": "vendor",
      "status": "in_progress",
      "subject": "Food delivered late and cold",
      "created_at": "2025-06-21T14:00:00Z"
    }
  ]
}
```

---

### 11.3 Get Complaint Details

Fetch full details of a specific complaint including admin response.

- **Method:** `GET`
- **URL:** `/api/v1/user/complaint/{complaint_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `complaint_id` | UUID | Yes |

**Response Fields:**

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Complaint ID |
| `user_id` | UUID | User who filed |
| `vendor_id` | UUID \| null | Vendor involved |
| `order_id` | UUID \| null | Related order |
| `subscription_id` | UUID \| null | Related subscription |
| `against` | string | `vendor` \| `platform` \| `delivery` \| `package` |
| `status` | string | `open` \| `in_progress` \| `resolved` \| `closed` \| `rejected` |
| `subject` | string | Complaint subject |
| `description` | string | Complaint description |
| `evidence_urls` | array \| null | Evidence URLs |
| `admin_notes` | string \| null | Notes from admin |
| `resolution` | string \| null | Resolution details |
| `resolved_at` | datetime \| null | Resolution timestamp |
| `created_at` | datetime \| null | Filed at |
| `updated_at` | datetime \| null | Last updated |

---

### 11.4 Update Complaint

Update subject, description, or add more evidence before resolution.

- **Method:** `PUT`
- **URL:** `/api/v1/user/complaint/{complaint_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `complaint_id` | UUID | Yes |

**Request Body (all optional):**

| Field | Type | Notes |
|-------|------|-------|
| `subject` | string | Updated subject (max 255 chars) |
| `description` | string | Updated description (10–2000 chars) |
| `evidence_urls` | array of string | Additional evidence URLs |

---

### 11.5 Withdraw Complaint

Withdraw/delete a complaint you filed.

- **Method:** `DELETE`
- **URL:** `/api/v1/user/complaint/{complaint_id}`
- **Auth:** Yes

**Path Parameters:**

| Param | Type | Required |
|-------|------|----------|
| `complaint_id` | UUID | Yes |

**Sample Response:**
```json
{
  "success": true,
  "message": "Complaint withdrawn successfully"
}
```

---

## 12. Quick Reference Table

| # | Name | Method | URL | Auth |
|---|------|--------|-----|------|
| 1 | Generate OTP | `POST` | `/api/v1/user/auth/generate-otp` | No |
| 2 | Verify OTP | `POST` | `/api/v1/user/auth/verify-otp` | No |
| 3 | Login | `POST` | `/api/v1/user/auth/login` | No |
| 4 | Get Profile | `GET` | `/api/v1/user/profile` | Yes |
| 5 | Update Profile | `PUT` | `/api/v1/user/profile` | Yes |
| 6 | Update Profile Image | `PUT` | `/api/v1/user/profile/image` | Yes |
| 7 | Add Address | `POST` | `/api/v1/user/address` | Yes |
| 8 | Get All Addresses | `GET` | `/api/v1/user/address` | Yes |
| 9 | Get Single Address | `GET` | `/api/v1/user/address/{address_id}` | Yes |
| 10 | Update Address | `PUT` | `/api/v1/user/address/{address_id}` | Yes |
| 11 | Delete Address | `DELETE` | `/api/v1/user/address/{address_id}` | Yes |
| 12 | Verify Pincode | `POST` | `/api/v1/location/verify-pincode` | No |
| 13 | List Packages | `GET` | `/api/v1/user/menu/packages` | Yes |
| 14 | Get Package Details | `GET` | `/api/v1/user/menu/packages/{package_id}` | Yes |
| 15 | Get Plan Options | `GET` | `/api/v1/user/subscription/plans/options` | Yes |
| 16 | List Subscription Plans | `GET` | `/api/v1/user/subscription/plans` | Yes |
| 17 | List Subscribed Packages | `GET` | `/api/v1/user/subscription/packages` | Yes |
| 18 | Create Subscription | `POST` | `/api/v1/user/subscription` | Yes |
| 19 | Get My Subscriptions | `GET` | `/api/v1/user/subscription` | Yes |
| 20 | Get Subscription Details | `GET` | `/api/v1/user/subscription/{subscription_id}` | Yes |
| 21 | Cancel Subscription | `PUT` | `/api/v1/user/subscription/{subscription_id}/cancel` | Yes |
| 22 | Pause Subscription | `PUT` | `/api/v1/user/subscription/{subscription_id}/pause` | Yes |
| 23 | Resume Subscription | `PUT` | `/api/v1/user/subscription/{subscription_id}/resume` | Yes |
| 24 | Place Extra Order | `POST` | `/api/v1/user/order/extra` | Yes |
| 25 | Get Extra Orders | `GET` | `/api/v1/user/order/extra` | Yes |
| 26 | Get Extra Order Details | `GET` | `/api/v1/user/order/extra/{order_id}` | Yes |
| 27 | Get Wallet Details | `GET` | `/api/v1/user/wallet` | Yes |
| 28 | Get Transaction History | `GET` | `/api/v1/user/wallet/transactions` | Yes |
| 29 | Recharge Wallet | `POST` | `/api/v1/user/wallet/recharge` | Yes |
| 30 | Add Review | `POST` | `/api/v1/user/review` | Yes |
| 31 | Get My Reviews | `GET` | `/api/v1/user/review` | Yes |
| 32 | Get Review Details | `GET` | `/api/v1/user/review/{review_id}` | Yes |
| 33 | Update Review | `PUT` | `/api/v1/user/review/{review_id}` | Yes |
| 34 | Delete Review | `DELETE` | `/api/v1/user/review/{review_id}` | Yes |
| 35 | Get Vendor Reviews | `GET` | `/api/v1/user/review/vendor/{vendor_id}` | Yes |
| 36 | Raise Complaint | `POST` | `/api/v1/user/complaint` | Yes |
| 37 | Get My Complaints | `GET` | `/api/v1/user/complaint` | Yes |
| 38 | Get Complaint Details | `GET` | `/api/v1/user/complaint/{complaint_id}` | Yes |
| 39 | Update Complaint | `PUT` | `/api/v1/user/complaint/{complaint_id}` | Yes |
| 40 | Withdraw Complaint | `DELETE` | `/api/v1/user/complaint/{complaint_id}` | Yes |

---

## Notes for Mobile Integration

### Authentication Flow
1. New user: Call **Generate OTP** → user enters OTP → Call **Verify OTP** → store the returned JWT token.
2. Returning user: Call **Login** → store the returned JWT token.
3. For all subsequent requests: attach the token as `Authorization: Bearer <token>`.

### Typical User Journey
1. Login / Register (OTP or Password)
2. Verify pincode (`/location/verify-pincode`) to check service availability
3. Complete profile (`/user/profile`)
4. Add delivery address (`/user/address`)
5. Browse packages (`/user/menu/packages`) with category and pincode filters
6. View package details (`/user/menu/packages/{id}`)
7. Choose: **Subscribe** (`/user/subscription`) or **Place one-time order** (`/user/order/extra`)
8. Top-up wallet before ordering (`/user/wallet/recharge`)
9. Track subscriptions and manage (pause / resume / cancel)
10. Review the vendor after delivery
11. Raise complaint if needed

### Content Types
- All JSON requests: `Content-Type: application/json`
- Profile image upload: `Content-Type: multipart/form-data`

### UUIDs
All IDs in this API are UUIDs (e.g., `550e8400-e29b-41d4-a716-446655440000`). Store and pass them as strings.

### Decimal Values
Price/amount fields are returned as strings representing decimal numbers (e.g., `"80.00"`). Parse as float/decimal on the client side.

### Dates
- Date fields use format: `YYYY-MM-DD` (e.g., `"2025-07-01"`)
- Datetime fields use ISO 8601 format: `"2025-06-21T10:30:00Z"` (UTC)
