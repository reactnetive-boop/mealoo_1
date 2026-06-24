from sqlalchemy.orm import Session

from app.models.cart_model import CartItem


class CartRepository:

    @staticmethod
    def get_by_user_and_package(
        db: Session,
        user_id,
        package_id,
    ) -> CartItem:
        return (
            db.query(CartItem)
            .filter(
                CartItem.user_reference_id == user_id,
                CartItem.package_reference_id == package_id,
            )
            .first()
        )

    @staticmethod
    def get_by_id(
        db: Session,
        cart_item_id,
    ) -> CartItem:
        return (
            db.query(CartItem)
            .filter(CartItem.cart_item_id == cart_item_id)
            .first()
        )

    @staticmethod
    def get_all_by_user(
        db: Session,
        user_id,
    ):
        return (
            db.query(CartItem)
            .filter(CartItem.user_reference_id == user_id)
            .order_by(CartItem.created_at.asc())
            .all()
        )

    @staticmethod
    def create(
        db: Session,
        data: dict,
    ) -> CartItem:
        item = CartItem(**data)
        db.add(item)
        db.flush()
        return item

    @staticmethod
    def delete(
        db: Session,
        item: CartItem,
    ) -> None:
        db.delete(item)

    @staticmethod
    def delete_by_package_ids(
        db: Session,
        user_id,
        package_ids: list,
    ) -> int:
        return (
            db.query(CartItem)
            .filter(
                CartItem.user_reference_id == user_id,
                CartItem.package_reference_id.in_(package_ids),
            )
            .delete(synchronize_session=False)
        )

    @staticmethod
    def delete_all_by_user(
        db: Session,
        user_id,
    ) -> int:
        return (
            db.query(CartItem)
            .filter(CartItem.user_reference_id == user_id)
            .delete(synchronize_session=False)
        )
