from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_review_service import AdminReviewService

router = APIRouter()


@router.get(
    "",
    summary="List All Reviews",
    description=(
        "**Fetch a paginated list of all user reviews across the platform.**\n\n"
        "Filter by:\n"
        "- `vendor_id`: reviews for a specific provider\n"
        "- `min_rating` / `max_rating`: filter by star rating (1–5)\n"
        "- `is_visible`: `true` for visible reviews, `false` for hidden\n\n"
        "**When to call:** On the admin content moderation screen to spot and hide inappropriate reviews."
    )
)
def list_reviews(
    vendor_id: Optional[UUID] = Query(None),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    max_rating: Optional[int] = Query(None, ge=1, le=5),
    is_visible: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminReviewService.list_reviews(
        db,
        vendor_id=str(vendor_id) if vendor_id else None,
        min_rating=min_rating,
        max_rating=max_rating,
        is_visible=is_visible,
        page=page,
        limit=limit
    )


@router.put(
    "/{review_id}/visibility",
    summary="Show or Hide a Review",
    description=(
        "**Toggle the visibility of a review on the platform.**\n\n"
        "Pass `is_visible=true` to show or `is_visible=false` to hide. "
        "Hidden reviews are not returned in user-facing review lists but remain in the database.\n\n"
        "**When to call:** During content moderation when a review violates community guidelines."
    )
)
def set_review_visibility(
    review_id: UUID,
    is_visible: bool = Query(...),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminReviewService.set_visibility(db, str(review_id), is_visible, current["admin_id"])


@router.delete(
    "/{review_id}",
    summary="Delete a Review",
    description=(
        "**Permanently delete a review from the platform.**\n\n"
        "Use only for reviews that violate policy and should be removed entirely. "
        "For temporary hiding, use `PUT /{review_id}/visibility` instead."
    )
)
def delete_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminReviewService.delete_review(db, str(review_id), current["admin_id"])
