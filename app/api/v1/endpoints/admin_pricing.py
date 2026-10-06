from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import client_ip
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.schemas.admin_schema import AdminPricingComponentUpdate, AdminPricingPreviewRequest
from app.services.admin_pricing_service import AdminPricingService

router = APIRouter()

COMPONENT_KEY = r"^[a-z_]{3,50}$"


@router.get(
    "",
    summary="Current Pricing Configuration",
    description=(
        "Every pricing component in force: SMS charge, payment gateway charge, packaging, delivery charge, "
        "Orleeno commission and the (internal) delivery partner payout."
    ),
)
def get_pricing(db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminPricingService.current(db)


@router.get("/history", summary="Pricing Change History")
def get_history(
    component_key: Optional[str] = Query(None, pattern=COMPONENT_KEY),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPricingService.history(db, component_key, limit)


@router.post(
    "/preview",
    summary="Preview a Price Breakdown",
    description="Prices an example with the current configuration, including the kitchen / partner / platform split.",
)
def preview(payload: AdminPricingPreviewRequest, db: Session = Depends(get_db), current=Depends(get_current_admin)):
    return AdminPricingService.preview(db, payload)


@router.put(
    "/{component_key}",
    summary="Change a Pricing Component",
    description=(
        "Creates a new version of the component (the old one stays in the history). Applies to checkouts from "
        "now on; existing subscriptions and orders keep their stored price. `change_reason` is required. "
        "**super_admin**."
    ),
)
def update_component(
    payload: AdminPricingComponentUpdate,
    request: Request,
    component_key: str = Path(..., pattern=COMPONENT_KEY),
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPricingService.update(db, component_key, payload, current["admin_id"], client_ip(request))
