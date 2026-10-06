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

    # Relative path ("uploads/package_images/<id>.jpg"); prefix with the API host
    image_url: str

    is_primary: bool

    display_order: int


class UserPackageListItemResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    package_id: UUID

    category_reference_id: UUID

    # The kitchen that sells and cooks this package (for Orleeno catalogue
    # packages this is the kitchen offering it, not the catalogue owner)
    provider_id: UUID

    provider_name: Optional[str] = None

    provider_area: Optional[str] = None

    is_predefined: bool = False

    package_name: str

    short_description: Optional[str]

    # Canonical "breakfast,lunch"; meal_slots is the same as a list
    meal_type: Optional[str]

    meal_slots: List[str] = []

    food_type: Optional[str]

    food_types: List[str] = []

    price: Decimal

    discounted_price: Optional[Decimal]

    is_subscription_available: bool

    subscription_price: Optional[Decimal]

    is_available: bool

    kitchen_open_today: bool = True

    primary_image: Optional[str] = None

    # Unambiguous price fields (computed by the pricing engine)
    base_price: Decimal

    selling_price: Decimal

    discount_amount: Decimal

    subscription_unit_price: Decimal


class UserPackageListResponse(BaseModel):

    success: bool

    total: int

    serviceable: bool = True

    packages: List[UserPackageListItemResponse]


class UserPackageDetailResponse(UserPackageListItemResponse):

    description: Optional[str]

    items: List[UserPackageItemResponse] = []

    images: List[UserPackageImageResponse] = []


class ServiceabilityResponse(BaseModel):

    success: bool

    pin_code: int

    serviceable: bool

    # ok | pincode_not_serviceable | no_kitchens
    status: str

    message: Optional[str] = None

    kitchens: int

    packages: int
