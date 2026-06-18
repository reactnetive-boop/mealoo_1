from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_content_service import AdminPackageService
from app.schemas.admin_schema import AdminCreatePackageRequest, AdminUpdatePackageRequest

router = APIRouter()


@router.post("")
def create_package(
    payload: AdminCreatePackageRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.create_package(db, payload, current["admin_id"])


@router.get("")
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


@router.get("/{package_id}")
def get_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.get_package(db, str(package_id))


@router.put("/{package_id}")
def update_package(
    package_id: UUID,
    payload: AdminUpdatePackageRequest,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.update_package(db, str(package_id), payload)


@router.delete("/{package_id}")
def delete_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminPackageService.delete_package(db, str(package_id))
