from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.repositories.menu_category_repository import MenuCategoryRepository


def _category_view(category) -> dict:
    return {
        "category_id": str(category.category_id),
        "category_name": category.category_name,
        "category_slug": category.category_slug,
        "description": category.description,
        "display_order": category.display_order,
    }


class MenuCategoryService:

    @staticmethod
    def get_menu_categories(db: Session):
        return [_category_view(c) for c in MenuCategoryRepository.get_all_active_categories(db=db)]

    @staticmethod
    def get_category(db: Session, category_id):
        category = MenuCategoryRepository.get_by_category_id(db=db, category_id=category_id)
        if not category:
            raise DomainError("Category not found", 404)
        return _category_view(category)
