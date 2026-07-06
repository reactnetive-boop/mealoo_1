from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_content_service import AdminPlanService
from app.schemas.admin_schema import AdminCreatePlanRequest, AdminUpdatePlanRequest

router = APIRouter()


@router.post(
    "",
    summary="Create Subscription Plan",
    description=(
        "**Create a new subscription plan that users can choose from.**\n\n"
        "Required: `meal_slot` (e.g. `lunch`, `all_slots`), `subscription_type` "
        "(e.g. `weekly`, `monthly`), `duration_days`, `discount_percent`, `free_skips`.\n\n"
        "Users see active plans on `GET /user/subscription/plans`. "
        "Only active plans appear in the user-facing listing.\n\n"
        "**Requires:** `super_admin` role."
    )
)
def create_plan(
    payload: AdminCreatePlanRequest,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPlanService.create_plan(db, payload)


@router.get(
    "",
    summary="List Subscription Plans",
    description=(
        "**Fetch all subscription plans — both active and inactive.**\n\n"
        "Filter by `is_active` to see only published plans. "
        "Use this on the admin plan management screen.\n\n"
        "**Note:** Users only see plans with `is_active=true` via `GET /user/subscription/plans`."
    )
)
def list_plans(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPlanService.list_plans(db, is_active=is_active)


@router.get(
    "/{plan_id}",
    summary="Get Plan Detail",
    description=(
        "**Fetch full details of a single subscription plan.**\n\n"
        "Use `plan_id` from the plans list to review or prepare an update."
    )
)
def get_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPlanService.get_plan(db, str(plan_id))


@router.put(
    "/{plan_id}",
    summary="Update Subscription Plan",
    description=(
        "**Edit an existing subscription plan's details or toggle its active status.**\n\n"
        "Setting `is_active=false` hides the plan from users immediately — "
        "existing subscriptions using this plan are not affected."
    )
)
def update_plan(
    plan_id: UUID,
    payload: AdminUpdatePlanRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPlanService.update_plan(db, str(plan_id), payload)
