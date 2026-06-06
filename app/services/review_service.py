from datetime import date

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.repositories.review_repository import ReviewRepository


class ReviewService:

    @staticmethod
    def add_review(
        db: Session,
        user_id: str,
        payload
    ):

        review_data = payload.model_dump()

        review_data["user_id"] = user_id

        if not review_data.get("review_date"):

            review_data["review_date"] = date.today()

        review = ReviewRepository.create(db, review_data)

        return {
            "success": True,
            "message": "Review added successfully",
            "review_id": str(review.id)
        }

    @staticmethod
    def get_my_reviews(
        db: Session,
        user_id: str
    ):

        reviews = ReviewRepository.get_all_by_user(db, user_id)

        return {
            "success": True,
            "total": len(reviews),
            "reviews": reviews
        }

    @staticmethod
    def get_review(
        db: Session,
        user_id: str,
        review_id
    ):

        review = ReviewRepository.get_by_id(db, review_id)

        if not review or not review.is_visible:

            raise HTTPException(
                status_code=404,
                detail="Review not found"
            )

        if str(review.user_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return review

    @staticmethod
    def update_review(
        db: Session,
        user_id: str,
        review_id,
        payload
    ):

        review = ReviewRepository.get_by_id(db, review_id)

        if not review or not review.is_visible:

            raise HTTPException(
                status_code=404,
                detail="Review not found"
            )

        if str(review.user_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        update_data = payload.model_dump(exclude_unset=True)

        updated_review = ReviewRepository.update(
            db, review, update_data
        )

        return {
            "success": True,
            "message": "Review updated successfully",
            "review_id": str(updated_review.id)
        }

    @staticmethod
    def delete_review(
        db: Session,
        user_id: str,
        review_id
    ):

        review = ReviewRepository.get_by_id(db, review_id)

        if not review or not review.is_visible:

            raise HTTPException(
                status_code=404,
                detail="Review not found"
            )

        if str(review.user_id) != user_id:

            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        ReviewRepository.delete(db, review)

        return {
            "success": True,
            "message": "Review deleted successfully"
        }

    @staticmethod
    def get_vendor_reviews(
        db: Session,
        vendor_id
    ):

        reviews = ReviewRepository.get_all_by_vendor(db, vendor_id)

        return {
            "success": True,
            "total": len(reviews),
            "reviews": reviews
        }
