from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin, require_super_admin
from app.services.admin_content_service import AdminPackageService
from app.schemas.admin_schema import AdminCreatePackageRequest, AdminUpdatePackageRequest

router = APIRouter()


@router.post(
    "",
    summary="Create Platform Package (Predefined)",
    description=(
        "**Create a platform-level predefined meal package that providers can adopt.**\n\n"
        "Predefined packages serve as templates. Providers can select them via "
        "`POST /provider/packages/select` to offer under their own brand without creating from scratch.\n\n"
        "**Requires:** `super_admin` role."
    )
)
def create_package(
    payload: AdminCreatePackageRequest,
    db: Session = Depends(get_db),
    current=Depends(require_super_admin)
):
    return AdminPackageService.create_package(db, payload, current["admin_id"])


@router.get(
    "",
    summary="List All Packages (Admin View)",
    description=(
        "**Fetch all meal packages across all providers.**\n\n"
        "Filter by `is_predefined`, `is_active`, `provider_id`, or `search` term. "
        "Use this to audit package content, moderate listings, or find packages needing review.\n\n"
        "**When to call:** On the admin package management screen."
    )
)
def list_packages(
    is_predefined: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    provider_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.list_packages(
        db, is_predefined=is_predefined, is_active=is_active,
        provider_id=str(provider_id) if provider_id else None,
        search=search, page=page, limit=limit
    )


@router.get(
    "/{package_id}",
    summary="Get Package Detail (Admin View)",
    description=(
        "**Fetch complete package details including items, images, and provider info.**\n\n"
        "Use `package_id` from the packages list. "
        "Use before editing or deactivating a package."
    )
)
def get_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.get_package(db, str(package_id))


@router.put(
    "/{package_id}",
    summary="Update Package (Admin)",
    description=(
        "**Edit a package's details or toggle `is_active` / `is_available` flags.**\n\n"
        "Setting `is_active=false` hides the package from user listings immediately. "
        "Use this when a provider violates listing guidelines."
    )
)
def update_package(
    package_id: UUID,
    payload: AdminUpdatePackageRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.update_package(db, str(package_id), payload)


@router.delete(
    "/{package_id}",
    summary="Delete Package (Admin)",
    description=(
        "**Permanently delete a meal package.**\n\n"
        "Cannot delete packages with active subscriptions. "
        "Use `PUT /{package_id}` with `is_active=false` to hide it from users instead."
    )
)
def delete_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.delete_package(db, str(package_id))
