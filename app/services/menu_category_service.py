from sqlalchemy.orm import Session

from app.repositories.menu_category_repository import (
    MenuCategoryRepository
)


class MenuCategoryService:

    @staticmethod
    def get_menu_categories(
        db: Session
    ):

        categories = (
            MenuCategoryRepository
            .get_all_active_categories(
                db=db
            )
        )

        response = []

        for category in categories:

            response.append({
                "category_id": str(
                    category.category_id
                ),
                "category_name": (
                    category.category_name
                ),
                "category_slug": (
                    category.category_slug
                ),
                "description": (
                    category.description
                ),
                "display_order": (
                    category.display_order
                )
            })

        return response