from typing import Optional, List
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AddUserAddressRequest(BaseModel):

    label: Optional[str] = Field(
        None,
        max_length=50,
        description="Home | Work | Other"
    )

    address_line1: str = Field(
        ...,
        description="House/flat number, street"
    )

    address_line2: Optional[str] = None

    landmark: Optional[str] = None

    city: str

    state: str

    pin_code: str = Field(
        ...,
        max_length=10
    )

    country: Optional[str] = Field(
        "IN",
        max_length=6
    )

    latitude: Optional[Decimal] = None

    longitude: Optional[Decimal] = None

    is_default: Optional[bool] = False


class UpdateUserAddressRequest(BaseModel):

    label: Optional[str] = Field(
        None,
        max_length=50
    )

    address_line1: Optional[str] = None

    address_line2: Optional[str] = None

    landmark: Optional[str] = None

    city: Optional[str] = None

    state: Optional[str] = None

    pin_code: Optional[str] = Field(
        None,
        max_length=10
    )

    country: Optional[str] = Field(
        None,
        max_length=6
    )

    latitude: Optional[Decimal] = None

    longitude: Optional[Decimal] = None

    is_default: Optional[bool] = None


class UserAddressResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    user_address_id: UUID

    user_reference_id: UUID

    label: Optional[str]

    address_line1: str

    address_line2: Optional[str]

    landmark: Optional[str]

    city: str

    state: str

    pin_code: str

    country: Optional[str]

    latitude: Optional[Decimal]

    longitude: Optional[Decimal]

    is_default: bool

    is_active: bool

    created_at: Optional[datetime]

    updated_at: Optional[datetime]


class UserAddressListResponse(BaseModel):

    success: bool

    total: int

    addresses: List[UserAddressResponse]
