from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_content_service import AdminPlanService
from app.schemas.admin_schema import AdminCreatePlanRequest, AdminUpdatePlanRequest

router = APIRouter()


@router.post("")
def create_plan(
    payload: AdminCreatePlanRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPlanService.create_plan(db, payload)


@router.get("")
def list_plans(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPlanService.list_plans(db, is_active=is_active)


@router.get("/{plan_id}")
def get_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPlanService.get_plan(db, str(plan_id))


@router.put("/{plan_id}")
def update_plan(
    plan_id: UUID,
    payload: AdminUpdatePlanRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPlanService.update_plan(db, str(plan_id), payload)
