from typing import List, Optional, Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from enum import Enum

from app.utils.validators import validate_evidence_urls


class DeliveryBoyComplaintAgainst(str, Enum):
    PLATFORM = "platform"
    PROVIDER = "provider"


class RaiseDeliveryBoyComplaintRequest(BaseModel):

    against: DeliveryBoyComplaintAgainst

    subject: str = Field(..., min_length=3, max_length=255)

    description: str = Field(..., min_length=10, max_length=2000)

    # Required when against = provider
    provider_id: Optional[UUID] = None

    # Optional reference to the specific order this complaint relates to
    order_id: Optional[UUID] = None

    # 'order' | 'extra_order'
    order_type: Optional[Literal["order", "extra_order"]] = Field(None, description="order or extra_order")

    evidence_urls: Optional[List[str]] = Field(
        default=[],
        max_length=5,
        description="Up to 5 https:// links to images or documents"
    )

    @field_validator("evidence_urls")
    @classmethod
    def _safe_urls(cls, value):
        return validate_evidence_urls(value)

    @model_validator(mode="after")
    def provider_required_when_against_provider(self):
        if self.against == DeliveryBoyComplaintAgainst.PROVIDER and not self.provider_id:
            raise ValueError("provider_id is required when complaining against a provider")
        return self


class UpdateDeliveryBoyComplaintRequest(BaseModel):

    subject: Optional[str] = Field(None, max_length=255)

    description: Optional[str] = Field(None, min_length=10, max_length=2000)

    evidence_urls: Optional[List[str]] = Field(None, max_length=5)

    @field_validator("evidence_urls")
    @classmethod
    def _safe_urls_update(cls, value):
        return validate_evidence_urls(value)


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
