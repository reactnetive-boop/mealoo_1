from datetime import date

from fastapi import HTTPException

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.review_repository import ReviewRepository
from app.repositories.provider_repository import ProviderRepository


class ReviewService:

    @staticmethod
    def add_review(
        db: Session,
        user_id: str,
        payload
    ):

        review_data = payload.model_dump()

        # Remap schema field names to renamed model column names
        review_data["vendor_reference_id"] = review_data.pop("vendor_id")
        review_data["package_reference_id"] = review_data.pop("package_id")
        review_data["order_reference_id"] = review_data.pop("order_id")
        review_data["subscription_reference_id"] = review_data.pop("subscription_id")

        review_data["user_reference_id"] = user_id

        # Validate vendor exists
        vendor = ProviderRepository.get_by_provider_id(
            db, review_data["vendor_reference_id"]
        )
        if not vendor:
            raise HTTPException(
                status_code=400,
                detail="Vendor not found"
            )

        if not review_data.get("review_date"):

            review_data["review_date"] = date.today()

        try:
            review = ReviewRepository.create(db, review_data)
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Review could not be saved. Check that vendor, package, order, and subscription IDs are valid."
            )

        return {
            "success": True,
            "message": "Review added successfully",
            "review_id": str(review.review_id)
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

        if str(review.user_reference_id) != user_id:

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

        if str(review.user_reference_id) != user_id:

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
            "review_id": str(updated_review.review_id)
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

        if str(review.user_reference_id) != user_id:

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
