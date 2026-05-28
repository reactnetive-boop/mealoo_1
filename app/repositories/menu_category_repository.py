from sqlalchemy.orm import Session

from app.models.menu_category_model import (
    MenuCategory
)


class MenuCategoryRepository:

    @staticmethod
    def get_all_active_categories(
        db: Session
    ):

        return (
            db.query(MenuCategory)
            .filter(
                MenuCategory.is_active == True
            )
            .order_by(
                MenuCategory.display_order.asc()
            )
            .all()
        )