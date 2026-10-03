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
        min_length=3,
        max_length=300,
        description="House/flat number, street"
    )

    address_line2: Optional[str] = Field(None, max_length=300)

    landmark: Optional[str] = Field(None, max_length=200)

    city: str = Field(..., min_length=2, max_length=100)

    state: str = Field(..., min_length=2, max_length=100)

    pin_code: str = Field(
        ...,
        pattern=r"^[1-9]\d{5}$",
        description="6-digit Indian pincode"
    )

    country: Optional[str] = Field(
        "IN",
        max_length=6
    )

    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)

    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)

    is_default: Optional[bool] = False


class UpdateUserAddressRequest(BaseModel):

    label: Optional[str] = Field(
        None,
        max_length=50
    )

    address_line1: Optional[str] = Field(None, min_length=3, max_length=300)

    address_line2: Optional[str] = Field(None, max_length=300)

    landmark: Optional[str] = Field(None, max_length=200)

    city: Optional[str] = Field(None, min_length=2, max_length=100)

    state: Optional[str] = Field(None, min_length=2, max_length=100)

    pin_code: Optional[str] = Field(
        None,
        pattern=r"^[1-9]\d{5}$"
    )

    country: Optional[str] = Field(
        None,
        max_length=6
    )

    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)

    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)

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
