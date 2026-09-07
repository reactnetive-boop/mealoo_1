from typing import List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator
from enum import Enum


class DeliveryBoyComplaintAgainst(str, Enum):
    PLATFORM = "platform"
    PROVIDER = "provider"


class RaiseDeliveryBoyComplaintRequest(BaseModel):

    against: DeliveryBoyComplaintAgainst

    subject: str = Field(..., max_length=255)

    description: str = Field(..., min_length=10, max_length=2000)

    # Required when against = provider
    provider_id: Optional[UUID] = None

    # Optional reference to the specific order this complaint relates to
    order_id: Optional[UUID] = None

    # 'order' | 'extra_order'
    order_type: Optional[str] = Field(None, description="order or extra_order")

    evidence_urls: Optional[List[str]] = Field(
        default=[],
        description="Image/document URLs as evidence"
    )

    @model_validator(mode="after")
    def provider_required_when_against_provider(self):
        if self.against == DeliveryBoyComplaintAgainst.PROVIDER and not self.provider_id:
            raise ValueError("provider_id is required when complaining against a provider")
        return self


class UpdateDeliveryBoyComplaintRequest(BaseModel):

    subject: Optional[str] = Field(None, max_length=255)

    description: Optional[str] = Field(None, min_length=10, max_length=2000)

    evidence_urls: Optional[List[str]] = None


class DeliveryBoyComplaintResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    delivery_boy_complaint_id: UUID
    delivery_boy_reference_id: UUID
    against: str
    provider_reference_id: Optional[UUID]
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


class DeliveryBoyComplaintListResponse(BaseModel):

    success: bool
    total: int
    complaints: List[DeliveryBoyComplaintResponse]
