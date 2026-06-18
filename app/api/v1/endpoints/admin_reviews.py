from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth_dependency import get_current_admin
from app.services.admin_review_service import AdminReviewService

router = APIRouter()


@router.get("")
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


@router.put("/{review_id}/visibility")
def set_review_visibility(
    review_id: UUID,
    is_visible: bool = Query(...),
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminReviewService.set_visibility(db, str(review_id), is_visible)


@router.delete("/{review_id}")
def delete_review(
    review_id: UUID,
    db: Session = Depends(get_db),
    current=Depends(get_current_admin)
):
    return AdminReviewService.delete_review(db, str(review_id))
