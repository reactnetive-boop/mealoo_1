from sqlalchemy.orm import Session

from app.models.review_model import Review


class ReviewRepository:

    @staticmethod
    def create(
        db: Session,
        review_data: dict
    ):

        review = Review(**review_data)

        db.add(review)

        db.flush()

        db.refresh(review)

        return review

    @staticmethod
    def get_by_id(
        db: Session,
        review_id
    ):

        return (
            db.query(Review)
            .filter(
                Review.review_id == review_id
            )
            .first()
        )

    @staticmethod
    def get_all_by_user(
        db: Session,
        user_id,
        offset: int = 0,
        limit: int | None = None,
    ):

        return (
            db.query(Review)
            .filter(
                Review.user_reference_id == user_id,
                Review.is_visible == True
            )
            .order_by(
                Review.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def count_by_user(db: Session, user_id) -> int:
        return (
            db.query(Review)
            .filter(
                Review.user_reference_id == user_id,
                Review.is_visible == True
            )
            .count()
        )

    @staticmethod
    def get_all_by_vendor(db: Session, vendor_id, limit: int = 100, offset: int = 0):
        return (
            db.query(Review)
            .filter(Review.vendor_reference_id == vendor_id, Review.is_visible == True)  # noqa: E712
            .order_by(Review.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def count_by_vendor(db: Session, vendor_id) -> int:
        return (
            db.query(Review)
            .filter(Review.vendor_reference_id == vendor_id, Review.is_visible == True)  # noqa: E712
            .count()
        )

    @staticmethod
    def update(
        db: Session,
        review: Review,
        update_data: dict
    ):

        for key, value in update_data.items():

            setattr(review, key, value)

        db.flush()

        db.refresh(review)

        return review

    @staticmethod
    def delete(
        db: Session,
        review: Review
    ):

        review.is_visible = False

        db.flush()

        db.refresh(review)

        return review
