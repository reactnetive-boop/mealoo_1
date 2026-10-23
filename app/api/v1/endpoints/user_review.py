from fastapi import APIRouter, Depends, Query

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.core.paging import Paging, paging
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
        "**Rate the package of a delivered order or subscription meal.**\n\n"
        "Send `order_id` (one-time order) or `subscription_order_id` (one meal; `subscription_id` alone "
        "rates the latest delivered meal), `package_rating` (1–5, the package's own rating), "
        "`vendor_rating` (1–5) and optionally `review_text`. Kitchen and package are taken from the order; "
        "`vendor_id` / `package_id` are only checked against it.\n\n"
        "One review per order / meal: submitting again updates it (`updated: true`). "
        "Only delivered food can be rated."
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
    page: Paging = Depends(paging),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return ReviewService.get_my_reviews(db, current_user["user_id"], page)


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
    "/package/{package_id}",
    summary="A Package's Rating and Reviews",
    description=(
        "Average of this package's own ratings (`rating_average`, `rating_count`, `rating_label`, e.g. "
        "\"4.0 (3 reviews)\" or \"No ratings yet\") and its latest reviews. Pass `provider_id` for an "
        "Orleeno catalogue package: each kitchen that cooks it has its own rating."
    ),
)
def get_package_reviews(
    package_id: UUID,
    provider_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return ReviewService.get_package_reviews(db, package_id, provider_id, page=page, limit=limit)


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
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return ReviewService.get_vendor_reviews(db, vendor_id, page=page, limit=limit)
