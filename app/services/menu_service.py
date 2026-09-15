from sqlalchemy.orm import Session

from app.models.menu_category_model import MenuCategory

from app.repositories.menu_repository import (
    MenuRepository
)
from app.repositories.provider_selected_package_repository import (
    ProviderSelectedPackageRepository
)

from fastapi import HTTPException

class MenuService:

    @staticmethod
    def create_package(
        db: Session,
        provider_id: str,
        request
    ):

        category = (
            db.query(MenuCategory)
            .filter(
                MenuCategory.category_id == request.category_id
            )
            .first()
        )

        if not category:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Category not found. "
                    "Use a category_id from GET /menu/categories."
                )
            )

        package_data = {

            "provider_id": provider_id,

            "category_reference_id": str(request.category_id),

            "package_name": (
                request.package_name
            ),

            "short_description": (
                request.short_description
            ),

            "description": (
                request.description
            ),

            "meal_type": (
                request.meal_type
            ),

            "food_type": (
                request.food_type
            ),

            "price": request.price,

            "discounted_price": (
                request.discounted_price
            ),

            "is_subscription_available": (
                request.is_subscription_available
            ),

            "subscription_price": (
                request.subscription_price
            ),

            # Providers cannot self-publish — an admin activates the package
            # via PUT /admin/packages/{package_id} with is_active=true
            "is_active": False
        }

        package = (
            MenuRepository.create_package(
                db,
                package_data
            )
        )

        ProviderSelectedPackageRepository.create(
            db,
            provider_id=provider_id,
            package_id=package.package_id
        )

        for item in request.items:

            item_data = {

                "package_reference_id": (
                    package.package_id
                ),

                "item_name": (
                    item.item_name
                ),

                "quantity": (
                    item.quantity
                )
            }

            (
                MenuRepository.create_package_item(
                    db,
                    item_data
                )
            )

        db.commit()

        return {

            "success": True,

            "message": (
                "Package created successfully"
            ),

            "package_id": str(
                package.package_id
            )
        }
    
    @staticmethod
    def get_package_details(
        db,
        package_id
    ):

        package = MenuRepository.get_package_by_id(
            db,
            package_id
        )

        if not package:

            raise HTTPException(
                status_code=404,
                detail="Package not found"
            )

        return package
    
    @staticmethod
    def list_provider_packages(
        db,
        provider_id,
        is_predefined: bool = False,
        current_provider_id: str = None
    ):

        if is_predefined:
            return MenuRepository.list_predefined_packages_not_selected(
                db,
                admin_id=provider_id,
                current_provider_id=current_provider_id
            )

        return MenuRepository.list_provider_packages(
            db,
            provider_id
        )
    
    @staticmethod
    def update_package(
        db,
        package_id,
        request
    ):

        package = MenuRepository.get_package_by_id(
            db,
            package_id
        )

        if not package:

            raise HTTPException(
                status_code=404,
                detail="Package not found"
            )

        update_data = request.dict(
            exclude_unset=True
        )

        return MenuRepository.update_package(
            db,
            package,
            update_data
        )
    
    @staticmethod
    def delete_package(
        db,
        package_id
    ):

        package = MenuRepository.get_package_by_id(
            db,
            package_id
        )

        if not package:

            raise HTTPException(
                status_code=404,
                detail="Package not found"
            )

        MenuRepository.delete_package(
            db,
            package
        )

        return {
            "success": True,
            "message": "Package deleted successfully"
        }