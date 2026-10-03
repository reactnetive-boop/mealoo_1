from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_provider
from app.schemas.menu_schema import (
    GetMenuCategoryListResponse,
    MenuCategoryResponse,
    CreateMenuPackageRequest,
    MenuPackageResponse,
    UpdateMenuPackageRequest,
)
from app.services.menu_service import MenuService
from app.services.menu_category_service import MenuCategoryService

router = APIRouter()


@router.get(
    "/categories",
    response_model=GetMenuCategoryListResponse,
    summary="List All Menu Categories",
    description="Active categories, in display order. Public (used by the kitchen and admin apps).",
)
def get_menu_categories(db: Session = Depends(get_db)):
    return {
        "success": True,
        "message": "Menu categories fetched successfully",
        "data": MenuCategoryService.get_menu_categories(db=db),
    }


@router.get(
    "/categories/{category_id}",
    response_model=MenuCategoryResponse,
    summary="Get Category Detail",
)
def get_menu_category(category_id: UUID, db: Session = Depends(get_db)):
    return MenuCategoryService.get_category(db=db, category_id=category_id)


@router.post(
    "/package",
    response_model=MenuPackageResponse,
    summary="Create a Meal Package",
    description=(
        "Creates a package for the logged-in kitchen. `price` is the base price (MRP), "
        "`discounted_price` the selling price (<= price, optional), `subscription_price` the "
        "per-meal subscription price (optional, defaults to the selling price). The package "
        "is `pending` until an admin approves it."
    ),
)
def create_package(
    request: CreateMenuPackageRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return MenuService.create_package(db, current_provider["provider_id"], request)


@router.get(
    "/catalog",
    summary="Orleeno Catalogue Packages",
    description="Ready-made packages created by Orleeno that the kitchen can add to its menu.",
)
def list_catalog(db: Session = Depends(get_db), current_provider=Depends(get_current_provider)):
    return MenuService.list_catalog(db, current_provider["provider_id"])


@router.get(
    "/get/{package_id}",
    summary="Get Package Detail (Provider View)",
    description="Own packages, catalogue packages and packages this kitchen offers only.",
)
def get_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return MenuService.get_package_details(db, current_provider["provider_id"], package_id)


@router.get(
    "/list/{provider_id}",
    summary="List Provider's Packages",
    description=(
        "Own packages (with approval status and rejection reason) and catalogue packages the "
        "kitchen offers. `provider_id` must be the logged-in kitchen."
    ),
)
def list_packages(
    provider_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    if str(provider_id) != current_provider["provider_id"]:
        raise HTTPException(status_code=403, detail="You can only list your own packages")
    return MenuService.list_provider_packages(db, current_provider["provider_id"])


@router.put(
    "/update/{package_id}",
    summary="Update a Meal Package",
    description="Own packages only. Changes to what customers buy send the package back for approval.",
)
def update_package(
    package_id: UUID,
    request: UpdateMenuPackageRequest,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return MenuService.update_package(db, current_provider["provider_id"], package_id, request)


@router.delete(
    "/delete/{package_id}",
    summary="Delete a Meal Package",
    description="Soft delete. Refused while running subscriptions use the package.",
)
def delete_package(
    package_id: UUID,
    db: Session = Depends(get_db),
    current_provider=Depends(get_current_provider),
):
    return MenuService.delete_package(db, current_provider["provider_id"], package_id)
