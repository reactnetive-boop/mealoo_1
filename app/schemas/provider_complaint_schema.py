from typing import List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator
from enum import Enum


class ProviderComplaintAgainst(str, Enum):
    PLATFORM = "platform"
    DELIVERY_BOY = "delivery_boy"


class RaiseProviderComplaintRequest(BaseModel):

    against: ProviderComplaintAgainst

    subject: str = Field(..., max_length=255)

    description: str = Field(..., min_length=10, max_length=2000)

    # Required when against = delivery_boy
    delivery_boy_id: Optional[UUID] = None

    # Optional reference to the specific order this complaint relates to
    order_id: Optional[UUID] = None

    # 'order' | 'extra_order'
    order_type: Optional[str] = Field(None, description="order or extra_order")

    evidence_urls: Optional[List[str]] = Field(
        default=[],
        description="Image/document URLs as evidence"
    )

    @model_validator(mode="after")
    def delivery_boy_required_when_against_delivery_boy(self):
        if self.against == ProviderComplaintAgainst.DELIVERY_BOY and not self.delivery_boy_id:
            raise ValueError("delivery_boy_id is required when complaining against a delivery boy")
        return self


class UpdateProviderComplaintRequest(BaseModel):

    subject: Optional[str] = Field(None, max_length=255)

    description: Optional[str] = Field(None, min_length=10, max_length=2000)

    evidence_urls: Optional[List[str]] = None


class ProviderComplaintResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    provider_complaint_id: UUID
    provider_reference_id: UUID
    against: str
    delivery_boy_reference_id: Optional[UUID]
    order_id: Optional[UUID]
    order_type: Optional[str]
    status: str
    subject: str
    description: str
    evidence_urls: Optional[List[str]]
    admin_notes: Optional[str]
    resolution: Optional[str]
    resolved_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class ProviderComplaintListResponse(BaseModel):

    success: bool
    total: int
    complaints: List[ProviderComplaintResponse]
