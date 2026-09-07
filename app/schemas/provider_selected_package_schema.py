from uuid import UUID
from typing import Optional

from pydantic import BaseModel, Field


class SelectPackageRequest(BaseModel):
    provider_id: UUID
    package_id: UUID
    daily_capacity: Optional[int] = Field(
        default=None,
        gt=0,
        description="Max units of this package the provider can serve per meal-slot per day. Omit for no limit."
    )


class UpdateCapacityRequest(BaseModel):
    provider_id: UUID
    package_id: UUID
    daily_capacity: Optional[int] = Field(
        default=None,
        gt=0,
        description="New capacity limit. Send null to remove the limit."
    )


class SelectPackageResponse(BaseModel):
    success: bool
    message: str
    daily_capacity: Optional[int] = None


class UpdateCapacityResponse(BaseModel):
    success: bool
    message: str
    daily_capacity: Optional[int]
    current_peak_demand: int