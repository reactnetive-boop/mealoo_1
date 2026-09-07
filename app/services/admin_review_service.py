from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.review_model import Review


class AdminReviewService:

    @staticmethod
    def list_reviews(db: Session, vendor_id: str = None, min_rating: int = None,
                     max_rating: int = None, is_visible: bool = None, page: int = 1, limit: int = 20):
        query = db.query(Review)
        if vendor_id:
            query = query.filter(Review.vendor_reference_id == vendor_id)
        if min_rating is not None:
            query = query.filter(Review.vendor_rating >= min_rating)
        if max_rating is not None:
            query = query.filter(Review.vendor_rating <= max_rating)
        if is_visible is not None:
            query = query.filter(Review.is_visible == is_visible)

        total = query.count()
        reviews = query.order_by(Review.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {"success": True, "total": total, "page": page, "reviews": reviews}

    @staticmethod
    def set_visibility(db: Session, review_id: str, is_visible: bool):
        review = db.query(Review).filter(Review.review_id == review_id).first()
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")

        review.is_visible = is_visible
        db.commit()

        action = "shown" if is_visible else "hidden"
        return {"success": True, "message": f"Review {action}"}

    @staticmethod
    def delete_review(db: Session, review_id: str):
        review = db.query(Review).filter(Review.review_id == review_id).first()
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")

        db.delete(review)
        db.commit()
        return {"success": True, "message": "Review deleted"}
