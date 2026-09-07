from typing import List, Optional
from uuid import UUID
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AddReviewRequest(BaseModel):

    vendor_id: UUID

    vendor_rating: int = Field(
        ...,
        ge=1,
        le=5,
        description="Provider rating 1–5"
    )

    package_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Package rating 1–5"
    )

    review_text: Optional[str] = Field(
        None,
        max_length=1000
    )

    package_id: Optional[UUID] = None

    order_id: Optional[UUID] = None

    subscription_id: Optional[UUID] = None

    review_date: Optional[date] = None


class UpdateReviewRequest(BaseModel):

    vendor_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5
    )

    package_rating: Optional[int] = Field(
        None,
        ge=1,
        le=5
    )

    review_text: Optional[str] = Field(
        None,
        max_length=1000
    )


class ReviewResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    review_id: UUID

    user_reference_id: UUID

    vendor_reference_id: UUID

    package_reference_id: Optional[UUID]

    order_reference_id: Optional[UUID]

    subscription_reference_id: Optional[UUID]

    vendor_rating: int

    package_rating: Optional[int]

    review_text: Optional[str]

    review_date: Optional[date]

    is_visible: bool

    created_at: Optional[datetime]

    updated_at: Optional[datetime]


class ReviewListResponse(BaseModel):

    success: bool

    total: int

    reviews: List[ReviewResponse]
