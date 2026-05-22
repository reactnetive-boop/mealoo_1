from sqlalchemy.orm import Session

from app.repositories.menu_repository import (
    MenuRepository
)


class MenuService:

    @staticmethod
    def create_package(
        db: Session,
        provider_id: str,
        request
    ):

        package_data = {

            "provider_id": provider_id,

            "category_id": request.category_id,

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
            )
        }

        package = (
            MenuRepository.create_package(
                db,
                package_data
            )
        )

        for item in request.items:

            item_data = {

                "package_id": (
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