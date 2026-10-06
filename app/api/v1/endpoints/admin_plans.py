from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_plan_service import AdminPlanService
from app.schemas.admin_schema import AdminCreatePlanRequest, AdminUpdatePlanRequest

router = APIRouter()


@router.post(
    "",
    summary="Create Subscription Plan",
    description=(
        "`subscription_type`: weekly | fortnightly | monthly | quarterly | half_yearly | annually | custom. "
        "`meal_slot`: breakfast | lunch | dinner | breakfast_lunch | lunch_dinner | breakfast_dinner | all_slots. "
        "Custom plans have no fixed `duration_days` (the customer picks start and end dates). **super_admin**."
    )
)
def create_plan(
    payload: AdminCreatePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPlanService.create_plan(db, payload, current["admin_id"], client_ip(request))


@router.get("", summary="List Subscription Plans")
def list_plans(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPlanService.list_plans(db, is_active=is_active)


@router.get("/{plan_id}", summary="Get Plan Detail")
def get_plan(plan_id: UUID, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminPlanService.get_plan(db, str(plan_id))


@router.put(
    "/{plan_id}",
    summary="Update Subscription Plan",
    description=(
        "Edit `free_skips`, `discount_percent`, `duration_days` or `is_active`. Changes apply to new subscriptions; "
        "running ones keep the terms they were bought with. **super_admin**."
    )
)
def update_plan(
    plan_id: UUID,
    payload: AdminUpdatePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPlanService.update_plan(db, str(plan_id), payload, current["admin_id"], client_ip(request))
