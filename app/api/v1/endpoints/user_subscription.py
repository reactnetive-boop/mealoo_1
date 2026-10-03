from fastapi import APIRouter, Depends, Query, Header

from sqlalchemy.orm import Session

from uuid import UUID

from datetime import date

from app.core.database import get_db
from app.core.rate_limit import limit_by_ip
from app.dependencies.auth_dependency import get_current_user
from app.schemas.subscription_schema import (
    SubscriptionPlanListResponse,
    SubscriptionPlanOptionsResponse,
    CreateSubscriptionRequest,
    SubscriptionQuoteRequest,
    CreateSubscriptionResponse,
    SubscriptionListResponse,
    SubscriptionResponse,
    CancelSubscriptionRequest,
    PauseSubscriptionResponse,
    ResumeSubscriptionResponse,
    PackageSwitchRequest,
    PackageSwitchPreviewResponse,
    PackageSwitchResponse,
    UserSubscriptionOrderListResponse,
    UserSubscriptionOrderDetailResponse,
    SkipOrderResponse,
)
from app.schemas.user_menu_schema import UserPackageListResponse
from app.services.subscription_service import SubscriptionService
from app.services.package_switch_service import PackageSwitchService

router = APIRouter()


@router.get(
    "/plans/options",
    response_model=SubscriptionPlanOptionsResponse,
    summary="Get Subscription Filter Options",
    description=(
        "**Fetch the distinct meal slot and subscription type values available in the system.**\n\n"
        "Use the returned lists to populate filter dropdowns on the subscription plans screen "
        "before calling `GET /user/subscription/plans`.\n\n"
        "**When to call:** When the user opens the 'Choose a Plan' screen for the first time."
    )
)
def get_plan_options(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.get_plan_options(db)


@router.get(
    "/plans",
    response_model=SubscriptionPlanListResponse,
    summary="List Subscription Plans",
    description=(
        "**Fetch available subscription plans with optional filters.**\n\n"
        "Filter by `meal_slot` (e.g. `breakfast`, `lunch`, `all_slots`) and/or "
        "`subscription_type` (e.g. `weekly`, `monthly`). "
        "Each plan includes `plan_id`, duration in days, price, discount %, and free skips allowed.\n\n"
        "**When to call:** After the user selects filters on the plans screen. "
        "The `plan_id` from this response is required when creating a subscription.\n\n"
        "**Flow:** `GET /plans/options` → user selects filters → `GET /plans` → select a plan → "
        "`POST /user/subscription`"
    )
)
def list_subscription_plans(
    meal_slot: str = Query(
        default=None,
        description="Filter by meal slot e.g. breakfast, lunch, dinner, breakfast_lunch, lunch_dinner, breakfast_dinner, all_slots"
    ),
    subscription_type: str = Query(
        default=None,
        description="Filter by subscription type e.g. weekly, monthly, quarterly, half_yearly, annually, custom"
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.list_plans(
        db,
        meal_slot=meal_slot,
        subscription_type=subscription_type
    )


@router.get(
    "/packages",
    summary="List My Subscribed Packages",
    description=(
        "**Fetch all meal packages across all of the user's active subscriptions.**\n\n"
        "Returns package details along with their linked subscription status, meal slot, "
        "and date range. Use this on the 'My Meals' or 'Active Plan' home screen.\n\n"
        "**Requires:** Bearer token from `POST /user/login`"
    )
)
def list_subscribed_packages(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.list_subscribed_packages(
        db,
        current_user["user_id"]
    )


@router.post(
    "",
    response_model=CreateSubscriptionResponse,
    summary="Create a New Subscription",
    description=(
        "**Subscribe to one or more meal packages from a single vendor.**\n\n"
        "**Required fields:**\n"
        "- `plan_id` — from `GET /user/subscription/plans`\n"
        "- `vendor_id` — `provider_id` from the package listing\n"
        "- `address_id` — from `GET /user/address`\n"
        "- `start_date` — when delivery should begin (YYYY-MM-DD)\n"
        "- `items` — list of `{package_id, quantity}`\n\n"
        "**What happens internally:** validates packages, checks provider capacity, "
        "calculates total after plan discount, verifies wallet balance, "
        "creates subscription + daily orders, and returns the subscription ID.\n\n"
        "**Prerequisite:** Wallet must have sufficient balance (`GET /user/wallet`). "
        "All packages must belong to the same vendor. Each package must be subscription-enabled.\n\n"
        "**Flow:** Browse packages → add to cart → check wallet → pick plan & address → "
        "`POST /user/subscription` → `GET /user/subscription` to confirm"
    )
)
def create_subscription(
    payload: CreateSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=80),
):

    return SubscriptionService.create_subscription(
        db,
        current_user["user_id"],
        payload,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/quote",
    summary="Price a Subscription (no charge)",
    description=(
        "Returns the exact breakdown `POST /user/subscription` would charge: package price, "
        "plan discount, every configured charge (delivery, packaging, SMS, payment gateway, "
        "Orleeno commission), the total, the wallet balance and any shortfall. All prices are "
        "computed on the server; the app only displays them."
    ),
    dependencies=[Depends(limit_by_ip("quote", 120, 60))],
)
def quote_subscription(
    payload: SubscriptionQuoteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return SubscriptionService.quote(db, current_user["user_id"], payload)


@router.get(
    "",
    response_model=SubscriptionListResponse,
    summary="List My Subscriptions",
    description=(
        "**Fetch all subscriptions (active, paused, expired, cancelled) for the logged-in user.**\n\n"
        "Each subscription includes its status, meal slot, date range, vendor, and total amount. "
        "Use `subscription_id` to fetch detailed info or to pause / cancel.\n\n"
        "**When to call:** On the 'My Subscriptions' screen or dashboard."
    )
)
def get_my_subscriptions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.get_my_subscriptions(
        db,
        current_user["user_id"]
    )


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Get Subscription Detail",
    description=(
        "**Fetch full details of a single subscription by its ID.**\n\n"
        "Returns plan info, packages, dates, status, and financial summary. "
        "Use `subscription_id` from `GET /user/subscription`.\n\n"
        "**When to call:** When the user taps on a subscription from the list screen."
    )
)
def get_subscription(
    subscription_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.get_subscription(
        db,
        current_user["user_id"],
        subscription_id
    )


@router.get(
    "/{subscription_id}/orders",
    response_model=UserSubscriptionOrderListResponse,
    summary="List Orders of a Subscription",
    description=(
        "**Fetch every daily meal order generated for one of the user's subscriptions.**\n\n"
        "Each subscription day is expanded into one order per meal slot "
        "(e.g. a `lunch_dinner` plan yields two orders per day). Orders are returned in "
        "date → meal-slot order and include the delivery `status`, the `otp_for_delivery` "
        "the user must share with the delivery partner, and `delivery_boy_reference_id` once assigned.\n\n"
        "Optional filters: `status` (`scheduled`, `preparing`, `out_for_delivery`, `delivered`, "
        "`skipped`, `cancelled`) and `order_date` (YYYY-MM-DD). "
        "`status_summary` gives a per-status count for progress indicators.\n\n"
        "**When to call:** On the 'Subscription Detail' → 'Meal Schedule' / 'Order History' screen, "
        "after `GET /user/subscription/{subscription_id}`.\n\n"
        "**Note:** Orders are generated by the scheduler shortly after the subscription is created; "
        "an empty list right after `POST /user/subscription` is expected briefly."
    )
)
def list_subscription_orders(
    subscription_id: UUID,
    status: str = Query(
        default=None,
        description="Filter by order status e.g. scheduled, preparing, out_for_delivery, delivered, skipped, cancelled"
    ),
    order_date: date = Query(
        default=None,
        description="Filter by delivery date (YYYY-MM-DD)"
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.list_subscription_orders(
        db,
        current_user["user_id"],
        subscription_id,
        status=status,
        order_date=order_date
    )


@router.get(
    "/{subscription_id}/orders/{order_id}",
    response_model=UserSubscriptionOrderDetailResponse,
    summary="Get Subscription Order Detail",
    description=(
        "**Fetch full details of a single meal order within a subscription.**\n\n"
        "Returns the order (status, date, meal slot, delivery OTP, delivered time), "
        "the delivery address, the subscribed packages being served, the provider (kitchen) "
        "contact info, and the assigned delivery partner (`null` until the provider assigns one).\n\n"
        "Use `order_id` from `GET /user/subscription/{subscription_id}/orders`.\n\n"
        "**When to call:** When the user taps an order on the meal schedule to track it "
        "or to read the OTP for hand-over."
    )
)
def get_subscription_order(
    subscription_id: UUID,
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.get_subscription_order(
        db,
        current_user["user_id"],
        subscription_id,
        order_id
    )


@router.put(
    "/{subscription_id}/orders/{order_id}/skip",
    response_model=SkipOrderResponse,
    summary="Skip a Subscription Order",
    description=(
        "**Skip one scheduled meal order of an active subscription.**\n\n"
        "The order is marked `skipped` and the provider / delivery partner will not serve it. "
        "Whether the skip is **free** (meal amount refunded to the wallet) depends on two rules:\n\n"
        "1. **Free skips left** — each plan grants `free_skips_total`; once "
        "`free_skips_used` reaches it, further skips are allowed but not refunded.\n"
        "2. **Same-day cutoff** — a skip on the order's own date must be requested before "
        "**06:00** for breakfast, **09:00** for lunch, **15:00** for dinner. After the cutoff the "
        "skip still goes through but is not free and does not consume a free skip. "
        "Future dates are always before the cutoff.\n\n"
        "A free skip credits the per-meal amount (`final_amount` ÷ serviceable meals) to the wallet "
        "with reason `free_skip_refund` and increments `free_skips_used`. "
        "`not_free_reason` (`cutoff_passed` / `no_free_skips_left`) tells the app why no refund was issued.\n\n"
        "**Rules:** only `scheduled` orders of an `active` subscription; past dates are rejected; "
        "a skipped order cannot be un-skipped.\n\n"
        "**When to call:** When the user taps 'Skip this meal' on the meal schedule / order detail screen "
        "(`GET /user/subscription/{subscription_id}/orders/{order_id}`). "
        "Show the cutoff and remaining free skips before confirming."
    )
)
def skip_subscription_order(
    subscription_id: UUID,
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.skip_order(
        db,
        current_user["user_id"],
        subscription_id,
        order_id
    )


@router.put(
    "/{subscription_id}/cancel",
    summary="Cancel Subscription",
    description=(
        "**Permanently cancel an active subscription.**\n\n"
        "Provide an optional `cancel_reason` in the request body. "
        "Cancelled subscriptions cannot be reactivated — the user must create a new one.\n\n"
        "**When to call:** When the user chooses 'Cancel Plan' from subscription settings.\n\n"
        "**Note:** To temporarily stop deliveries, use `PUT /{subscription_id}/pause` instead."
    )
)
def cancel_subscription(
    subscription_id: UUID,
    payload: CancelSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.cancel_subscription(
        db,
        current_user["user_id"],
        subscription_id,
        payload
    )


@router.post(
    "/{subscription_id}/switch/preview",
    response_model=PackageSwitchPreviewResponse,
    summary="Preview a Package Switch",
    description=(
        "**Calculate the cost of switching to another package without committing.**\n\n"
        "Uses the Unused Service Value Method: the remaining (unused) value of the "
        "current package is compared with the remaining cost of the new package over "
        "the same period. The switch always becomes effective from the **next service day** — "
        "today's meal is still served by the current provider.\n\n"
        "- `action = payment_required` → upgrade: `payment_amount` must be paid from the wallet\n"
        "- `action = wallet_credit` → downgrade: `wallet_credit_amount` will be credited\n"
        "- `action = no_adjustment` → same price: switch completes with no money movement\n\n"
        "Amounts follow the Floor (Truncate) Rule — fractional paise are discarded.\n"
        "Works for same-provider and different-provider switches alike.\n\n"
        "**When to call:** On the 'Switch Package' confirmation screen, before showing "
        "the user what they will pay or receive.\n\n"
        "**Flow:** browse packages → `POST /switch/preview` → confirm → `POST /switch`"
    )
)
def preview_package_switch(
    subscription_id: UUID,
    payload: PackageSwitchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return PackageSwitchService.preview_switch(
        db,
        current_user["user_id"],
        subscription_id,
        payload
    )


@router.post(
    "/{subscription_id}/switch",
    response_model=PackageSwitchResponse,
    summary="Switch to Another Package",
    description=(
        "**Switch the subscription to a different package (same or different provider).**\n\n"
        "Applies the calculation shown by `POST /switch/preview`:\n"
        "- **Upgrade** — the difference is debited from the wallet immediately. "
        "If the balance is insufficient the switch is cancelled and nothing changes.\n"
        "- **Downgrade** — the difference (floored to whole rupees) is credited to the wallet.\n"
        "- **Same price** — no money movement.\n\n"
        "**What happens internally:** the old subscription is closed after today's service "
        "(status `switched`), its future orders are cancelled, a new subscription is created "
        "for the remaining days with the new package/provider, new daily orders are generated, "
        "an audit record is stored, and the customer plus affected delivery partners are notified. "
        "Old and new providers are each settled only for the meals they actually serve.\n\n"
        "**Rules:** not allowed on the last day of the subscription; only active "
        "subscriptions can switch; switching to the currently subscribed package is rejected; "
        "the new package must be subscription-enabled and have capacity.\n\n"
        "**When to call:** After the user confirms the preview on the 'Switch Package' screen."
    )
)
def switch_package(
    subscription_id: UUID,
    payload: PackageSwitchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return PackageSwitchService.switch_package(
        db,
        current_user["user_id"],
        subscription_id,
        payload
    )


@router.put(
    "/{subscription_id}/pause",
    response_model=PauseSubscriptionResponse,
    summary="Pause Subscription",
    description=(
        "**Temporarily pause an active subscription starting from tomorrow.**\n\n"
        "All scheduled orders from the pause date onwards are cancelled automatically. "
        "The subscription end date is extended when resumed to compensate for paused days.\n\n"
        "**When to call:** When the user is going on vacation or wants to stop meals temporarily. "
        "Use `PUT /{subscription_id}/resume` to restart.\n\n"
        "**Note:** Cannot pause if the subscription ends before tomorrow."
    )
)
def pause_subscription(
    subscription_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.pause_subscription(
        db,
        current_user["user_id"],
        subscription_id
    )


@router.put(
    "/{subscription_id}/resume",
    response_model=ResumeSubscriptionResponse,
    summary="Resume Paused Subscription",
    description=(
        "**Resume a paused subscription starting from tomorrow.**\n\n"
        "The subscription end date is automatically extended by the number of days it was paused. "
        "Cancelled orders in the resumed window are reactivated and new orders are created "
        "for the extended period.\n\n"
        "**When to call:** After `PUT /{subscription_id}/pause` when the user is ready to restart deliveries."
    )
)
def resume_subscription(
    subscription_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return SubscriptionService.resume_subscription(
        db,
        current_user["user_id"],
        subscription_id
    )
