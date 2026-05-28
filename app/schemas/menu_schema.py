from typing import List
from typing import Optional

from pydantic import BaseModel
from uuid import UUID

class MenuCategoryResponse(
    BaseModel
):
    category_id: str
    category_name: str
    category_slug: str
    description: str | None = None
    display_order: int


class GetMenuCategoryListResponse(
    BaseModel
):
    success: bool
    message: str
    data: List[
        MenuCategoryResponse
    ]

class PackageItemRequest(
    BaseModel
):

    item_name: str

    quantity: Optional[str] = None


class CreateMenuPackageRequest(
    BaseModel
):

    category_id: str

    package_name: str

    short_description: Optional[str] = None

    description: Optional[str] = None

    meal_type: str

    food_type: str

    price: float

    discounted_price: Optional[float] = None

    is_subscription_available: bool = False

    subscription_price: Optional[float] = None

    items: List[PackageItemRequest]


class MenuPackageResponse(
    BaseModel
):

    success: bool

    message: str

    package_id: str

class PackageItemResponse(
    BaseModel
):

    item_id: UUID

    item_name: str

    quantity: Optional[str] = None

    class Config:

        from_attributes = True

class PackageImageResponse(
    BaseModel
):

    image_id: UUID

    image_url: str

    is_primary: bool

    class Config:

        from_attributes = True

class GetMenuPackageResponse(
    BaseModel
):

    package_id: UUID

    package_name: str

    short_description: Optional[str]

    description: Optional[str]

    meal_type: str

    food_type: str

    price: float

    discounted_price: Optional[float]

    items: List[PackageItemResponse] = []

    images: List[PackageImageResponse] = []

    class Config:

        from_attributes = True

class UpdateMenuPackageRequest(
    BaseModel
):

    package_name: Optional[str] = None

    short_description: Optional[str] = None

    description: Optional[str] = None

    meal_type: Optional[str] = None

    food_type: Optional[str] = None

    price: Optional[float] = None

    discounted_price: Optional[float] = None

    is_subscription_available: Optional[bool] = None

    subscription_price: Optional[float] = None

class CommonResponse(
    BaseModel
):

    success: bool

    message: str
