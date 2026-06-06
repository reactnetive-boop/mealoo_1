from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from uuid import UUID

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_user
from app.schemas.review_schema import (
    AddReviewRequest,
    UpdateReviewRequest,
    ReviewResponse,
    ReviewListResponse
)
from app.services.review_service import ReviewService

router = APIRouter()


@router.post("")
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
    response_model=ReviewListResponse
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
    response_model=ReviewResponse
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


@router.put("/{review_id}")
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


@router.delete("/{review_id}")
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
    response_model=ReviewListResponse
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
