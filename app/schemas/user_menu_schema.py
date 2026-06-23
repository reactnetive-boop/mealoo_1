from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class UserPackageItemResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    item_id: UUID

    item_name: str

    quantity: Optional[str]

    item_order: int


class UserPackageImageResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    image_id: UUID

    image_url: str

    is_primary: bool

    display_order: int


class UserPackageListItemResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    package_id: UUID

    category_reference_id: UUID

    provider_id: UUID

    package_name: str

    short_description: Optional[str]

    meal_type: Optional[str]

    food_type: Optional[str]

    price: Decimal

    discounted_price: Optional[Decimal]

    is_subscription_available: bool

    subscription_price: Optional[Decimal]

    is_available: bool

    primary_image: Optional[str] = None


class UserPackageListResponse(BaseModel):

    success: bool

    total: int

    packages: List[UserPackageListItemResponse]


class UserPackageDetailResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    package_id: UUID

    category_reference_id: UUID

    provider_id: UUID

    package_name: str

    short_description: Optional[str]

    description: Optional[str]

    meal_type: Optional[str]

    food_type: Optional[str]

    price: Decimal

    discounted_price: Optional[Decimal]

    is_subscription_available: bool

    subscription_price: Optional[Decimal]

    is_available: bool

    items: List[UserPackageItemResponse] = []

    images: List[UserPackageImageResponse] = []
