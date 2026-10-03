from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.review_schema import (
    AddReviewRequest,
    UpdateReviewRequest,
    ReviewResponse,
    ReviewListResponse,
    PublicReviewListResponse,
)
from app.services.review_service import ReviewService

router = APIRouter()


@router.post(
    "",
    summary="Submit a Review",
    description=(
        "**Rate and review a vendor after receiving a delivery.**\n\n"
        "Required: `vendor_id` (the vendor's `provider_id`) and `vendor_rating` (1–5). "
        "Optional: `package_id`, `order_id`, `subscription_id`, `package_rating`, `review_text`, `review_date`.\n\n"
        "Only one review per user per vendor per day is allowed (unique constraint). "
        "The vendor must exist — use `provider_id` from the package listing.\n\n"
        "**When to call:** After an order is delivered (`status = delivered`). "
        "Show a 'Rate your meal' prompt on the order detail screen.\n\n"
        "**Flow:** Order delivered → `POST /user/review` → `GET /user/review` to see your reviews"
    )
)
def add_review(
    payload: AddReviewRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ReviewService.add_review(
        db,
        current_user["user_id"],
        payload
    )


@router.get(
    "",
    response_model=ReviewListResponse,
    summary="List My Reviews",
    description=(
        "**Fetch all reviews submitted by the logged-in user.**\n\n"
        "Returns reviews in descending order of creation. "
        "Use `review_id` from this list to update or delete a specific review.\n\n"
        "**When to call:** On the user's profile 'My Reviews' section."
    )
)
def get_my_reviews(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ReviewService.get_my_reviews(
        db,
        current_user["user_id"]
    )


@router.get(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Get Review Detail",
    description=(
        "**Fetch a specific review by its ID.**\n\n"
        "Use `review_id` from `GET /user/review`. "
        "Returns the full review including ratings, text, and associated vendor/package.\n\n"
        "**When to call:** When the user taps on a review to view or edit it."
    )
)
def get_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ReviewService.get_review(
        db,
        current_user["user_id"],
        review_id
    )


@router.put(
    "/{review_id}",
    summary="Update a Review",
    description=(
        "**Edit the rating or text of an existing review.**\n\n"
        "Send only the fields to update (`vendor_rating`, `package_rating`, `review_text`). "
        "Use `review_id` from `GET /user/review`.\n\n"
        "**When to call:** When the user edits a review from 'My Reviews'."
    )
)
def update_review(
    review_id: UUID,
    payload: UpdateReviewRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ReviewService.update_review(
        db,
        current_user["user_id"],
        review_id,
        payload
    )


@router.delete(
    "/{review_id}",
    summary="Delete a Review",
    description=(
        "**Soft-delete (hide) a review.**\n\n"
        "The review is marked as not visible rather than permanently deleted. "
        "It will no longer appear in listings.\n\n"
        "**When to call:** When the user taps 'Delete' on a review from 'My Reviews'."
    )
)
def delete_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ReviewService.delete_review(
        db,
        current_user["user_id"],
        review_id
    )


@router.get(
    "/vendor/{vendor_id}",
    response_model=PublicReviewListResponse,
    summary="Get All Reviews for a Vendor",
    description=(
        "**Fetch all public reviews left for a specific vendor.**\n\n"
        "Use `vendor_id` (the vendor's `provider_id` UUID). "
        "Display these on the vendor detail / package detail page to help users decide.\n\n"
        "**When to call:** When rendering the vendor profile or package detail screen."
    )
)
def get_vendor_reviews(
    vendor_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    return ReviewService.get_vendor_reviews(
        db,
        vendor_id
    )
