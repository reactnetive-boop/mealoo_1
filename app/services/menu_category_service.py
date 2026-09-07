from fastapi import HTTPException

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

    @staticmethod
    def get_category(
        db: Session,
        category_id
    ):

        category = (
            MenuCategoryRepository
            .get_by_category_id(
                db=db,
                category_id=category_id
            )
        )

        if not category:

            raise HTTPException(
                status_code=404,
                detail="Category not found"
            )

        return {
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
        }