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

        db.commit()

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
        user_id
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
            .all()
        )

    @staticmethod
    def get_all_by_vendor(
        db: Session,
        vendor_id
    ):

        return (
            db.query(Review)
            .filter(
                Review.vendor_reference_id == vendor_id,
                Review.is_visible == True
            )
            .order_by(
                Review.created_at.desc()
            )
            .all()
        )

    @staticmethod
    def update(
        db: Session,
        review: Review,
        update_data: dict
    ):

        for key, value in update_data.items():

            setattr(review, key, value)

        db.commit()

        db.refresh(review)

        return review

    @staticmethod
    def delete(
        db: Session,
        review: Review
    ):

        review.is_visible = False

        db.commit()

        db.refresh(review)

        return review
