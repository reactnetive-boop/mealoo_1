from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import today_local
from app.core.errors import DomainError
from app.core.paging import FIRST_PAGE, Paging
from app.models.extra_order_model import ExtraOrder
from app.models.order_model import Order
from app.models.subscription_model import Subscription
from app.models.subscription_package_model import SubscriptionPackage
from app.repositories.review_repository import ReviewRepository


def _owned_review(db: Session, user_id: str, review_id):
    review = ReviewRepository.get_by_id(db, review_id)
    if not review or not review.is_visible or str(review.user_reference_id) != user_id:
        raise DomainError("Review not found", 404)
    return review


class ReviewService:

    @staticmethod
    def add_review(db: Session, user_id: str, payload):
        """
        Reviews are only accepted for food the customer actually received:
        a delivered one-time order, or a subscription with a delivered meal.
        The kitchen and package are taken from that order, not the request.
        """

        vendor_id = None
        package_ids: set = set()

        subscription_id = payload.subscription_id
        if payload.subscription_order_id:
            meal = db.query(Order).filter(
                Order.order_id == payload.subscription_order_id,
                Order.user_reference_id == user_id,
            ).first()
            if meal is None or meal.status != "delivered":
                raise DomainError("You can review a meal only after it has been delivered")
            if subscription_id and str(subscription_id) != str(meal.subscription_reference_id):
                raise DomainError("The meal does not belong to that subscription")
            subscription_id = meal.subscription_reference_id

        if payload.order_id:
            order = db.query(ExtraOrder).filter(
                ExtraOrder.extra_order_id == payload.order_id,
                ExtraOrder.user_reference_id == user_id,
            ).first()
            if order is None or order.status != "delivered":
                raise DomainError("You can review an order only after it has been delivered")
            vendor_id = order.vendor_reference_id
            package_ids = {order.package_reference_id}
        elif subscription_id:
            sub = db.query(Subscription).filter(
                Subscription.subscription_id == subscription_id,
                Subscription.user_reference_id == user_id,
            ).first()
            delivered = sub and db.query(Order).filter(
                Order.subscription_reference_id == sub.subscription_id,
                Order.status == "delivered",
            ).first()
            if not delivered:
                raise DomainError("You can review a subscription after a meal has been delivered")
            vendor_id = sub.vendor_reference_id
            package_ids = {
                p.package_reference_id
                for p in db.query(SubscriptionPackage).filter(
                    SubscriptionPackage.subscription_reference_id == sub.subscription_id
                )
            }
        else:
            raise DomainError("Choose the delivered order or subscription you are reviewing")

        if payload.vendor_id and str(payload.vendor_id) != str(vendor_id):
            raise DomainError("The kitchen does not match the order")
        if payload.package_id and payload.package_id not in package_ids:
            raise DomainError("The package does not match the order")

        try:
            review = ReviewRepository.create(db, {
                "user_reference_id": user_id,
                "vendor_reference_id": vendor_id,
                "package_reference_id": payload.package_id or (next(iter(package_ids)) if package_ids else None),
                "order_reference_id": payload.order_id,
                "subscription_reference_id": subscription_id,
                "subscription_order_reference_id": payload.subscription_order_id,
                "vendor_rating": payload.vendor_rating,
                "package_rating": payload.package_rating,
                "review_text": payload.review_text,
                "review_date": today_local(),
            })
        except IntegrityError:
            db.rollback()
            raise DomainError("You have already reviewed this kitchen today", 409) from None
        db.commit()

        return {"success": True, "message": "Review added successfully", "review_id": str(review.review_id)}

    @staticmethod
    def get_my_reviews(db: Session, user_id: str, paging: Paging = FIRST_PAGE):
        reviews = ReviewRepository.get_all_by_user(db, user_id, paging.offset, paging.limit)
        return {"success": True, **paging.meta(ReviewRepository.count_by_user(db, user_id)), "reviews": reviews}

    @staticmethod
    def get_review(db: Session, user_id: str, review_id):
        return _owned_review(db, user_id, review_id)

    @staticmethod
    def update_review(db: Session, user_id: str, review_id, payload):
        review = _owned_review(db, user_id, review_id)
        updated = ReviewRepository.update(db, review, payload.model_dump(exclude_unset=True))
        db.commit()
        return {"success": True, "message": "Review updated successfully", "review_id": str(updated.review_id)}

    @staticmethod
    def delete_review(db: Session, user_id: str, review_id):
        review = _owned_review(db, user_id, review_id)
        ReviewRepository.delete(db, review)
        db.commit()
        return {"success": True, "message": "Review deleted successfully"}

    @staticmethod
    def get_vendor_reviews(db: Session, vendor_id, page: int = 1, limit: int = 100):
        reviews = ReviewRepository.get_all_by_vendor(db, vendor_id, limit=limit, offset=(page - 1) * limit)
        # Other customers' reviews: no customer identifiers in the public view
        return {
            "success": True,
            "total": ReviewRepository.count_by_vendor(db, vendor_id),
            "page": page,
            "reviews": [
                {
                    "review_id": r.review_id,
                    "vendor_reference_id": r.vendor_reference_id,
                    "package_reference_id": r.package_reference_id,
                    "vendor_rating": r.vendor_rating,
                    "package_rating": r.package_rating,
                    "review_text": r.review_text,
                    "review_date": r.review_date,
                    "created_at": r.created_at,
                }
                for r in reviews
            ],
        }
