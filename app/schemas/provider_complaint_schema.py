from typing import List, Optional, Literal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from enum import Enum

from app.utils.validators import validate_evidence_urls


class ProviderComplaintAgainst(str, Enum):
    PLATFORM = "platform"
    DELIVERY_BOY = "delivery_boy"


class RaiseProviderComplaintRequest(BaseModel):

    against: ProviderComplaintAgainst

    subject: str = Field(..., min_length=3, max_length=255)

    description: str = Field(..., min_length=10, max_length=2000)

    # Required when against = delivery_boy
    delivery_boy_id: Optional[UUID] = None

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
    def delivery_boy_required_when_against_delivery_boy(self):
        if self.against == ProviderComplaintAgainst.DELIVERY_BOY and not self.delivery_boy_id:
            raise ValueError("delivery_boy_id is required when complaining against a delivery boy")
        return self


class UpdateProviderComplaintRequest(BaseModel):

    subject: Optional[str] = Field(None, max_length=255)

    description: Optional[str] = Field(None, min_length=10, max_length=2000)

    evidence_urls: Optional[List[str]] = Field(None, max_length=5)

    @field_validator("evidence_urls")
    @classmethod
    def _safe_urls_update(cls, value):
        return validate_evidence_urls(value)


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
