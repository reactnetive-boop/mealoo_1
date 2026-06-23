from typing import List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


class ComplaintAgainst(str, Enum):
    VENDOR = "vendor"
    PLATFORM = "platform"
    DELIVERY = "delivery"
    PACKAGE = "package"


class RaiseComplaintRequest(BaseModel):

    against: ComplaintAgainst

    subject: str = Field(
        ...,
        max_length=255
    )

    description: str = Field(
        ...,
        min_length=10,
        max_length=2000
    )

    vendor_id: Optional[UUID] = None

    order_id: Optional[UUID] = None

    subscription_id: Optional[UUID] = None

    evidence_urls: Optional[List[str]] = Field(
        default=[],
        description="List of image/document URLs as evidence"
    )


class UpdateComplaintRequest(BaseModel):

    subject: Optional[str] = Field(
        None,
        max_length=255
    )

    description: Optional[str] = Field(
        None,
        min_length=10,
        max_length=2000
    )

    evidence_urls: Optional[List[str]] = None


class ComplaintResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    complaint_id: UUID

    user_reference_id: UUID

    vendor_reference_id: Optional[UUID]

    order_reference_id: Optional[UUID]

    subscription_reference_id: Optional[UUID]

    against: str

    status: str

    subject: str

    description: str

    evidence_urls: Optional[List[str]]

    admin_notes: Optional[str]

    resolution: Optional[str]

    resolved_at: Optional[datetime]

    created_at: Optional[datetime]

    updated_at: Optional[datetime]


class ComplaintListResponse(BaseModel):

    success: bool

    total: int

    complaints: List[ComplaintResponse]
