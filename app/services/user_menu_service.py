from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.menu_repository import MenuRepository


class UserMenuService:

    @staticmethod
    def list_packages(
        db: Session,
        pin_code: int
    ):

        results = (
            MenuRepository
            .get_packages_by_pincode(
                db,
                pin_code
            )
        )

        package_list = []

        for psp, pkg in results:

            primary_image = None

            for img in pkg.images:

                if img.is_primary:

                    primary_image = img.image_url

                    break

            package_list.append({
                "package_id": pkg.package_id,
                "category_reference_id": pkg.category_reference_id,
                "provider_id": psp.provider_id,
                "package_name": pkg.package_name,
                "short_description": pkg.short_description,
                "meal_type": pkg.meal_type,
                "food_type": pkg.food_type,
                "price": pkg.price,
                "discounted_price": pkg.discounted_price,
                "is_subscription_available": pkg.is_subscription_available,
                "subscription_price": pkg.subscription_price,
                "is_available": pkg.is_available,
                "primary_image": primary_image
            })

        return {
            "success": True,
            "total": len(package_list),
            "packages": package_list
        }

    @staticmethod
    def get_package(
        db: Session,
        package_id
    ):

        package = (
            MenuRepository
            .get_active_package_by_id(
                db,
                package_id
            )
        )

        if not package:

            raise HTTPException(
                status_code=404,
                detail="Package not found or unavailable"
            )

        return package
