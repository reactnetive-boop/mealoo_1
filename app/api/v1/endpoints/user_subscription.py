from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.subscription_schema import (
    SubscriptionPlanListResponse,
    SubscriptionPlanOptionsResponse,
    CreateSubscriptionRequest,
    CreateSubscriptionResponse,
    SubscriptionListResponse,
    SubscriptionResponse,
    CancelSubscriptionRequest,
    PauseSubscriptionResponse,
    ResumeSubscriptionResponse,
    PackageSwitchRequest,
    PackageSwitchPreviewResponse,
    PackageSwitchResponse,
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
    current_user=Depends(get_current_user)
):

    return SubscriptionService.create_subscription(
        db,
        current_user["user_id"],
        payload
    )


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
