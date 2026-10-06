from typing import List
from typing import Optional
from typing import Union

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from uuid import UUID

from decimal import Decimal

from app.utils.meal_type import normalize_meal_type, normalize_food_type

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

    item_name: str = Field(..., min_length=1, max_length=255)

    quantity: Optional[str] = Field(None, max_length=100)


def _zero_is_none(value):
    # Older app versions send 0 for "no discount / no subscription price"
    if value is None:
        return None
    return None if Decimal(str(value)) <= 0 else value


class CreateMenuPackageRequest(
    BaseModel
):

    category_id: UUID = Field(
        ...,
        description="category_id from GET /menu/categories"
    )

    package_name: str = Field(..., min_length=2, max_length=255)

    short_description: Optional[str] = Field(None, max_length=500)

    description: Optional[str] = Field(None, max_length=5000)

    meal_type: Union[str, List[str]] = Field(
        ...,
        description=(
            "Meal slots this package is served in — one, any two, or all three. "
            "Send a list ([\"lunch\", \"dinner\"]), a comma separated string "
            "(\"lunch, dinner\") or \"full_day\" for all three."
        ),
        examples=[["lunch", "dinner"]]
    )

    food_type: Union[str, List[str]] = Field(
        ...,
        description="One or more of veg, non_veg, egg, vegan, jain"
    )

    @field_validator("meal_type", mode="after")
    @classmethod
    def _normalize_meal_type(cls, value):
        return normalize_meal_type(value)

    @field_validator("food_type", mode="after")
    @classmethod
    def _normalize_food_type(cls, value):
        return normalize_food_type(value)

    # Base price / MRP per meal
    price: Decimal = Field(..., gt=0, le=100000)

    # SELLING price for one-time orders (<= price). Omit for no discount.
    discounted_price: Optional[Decimal] = Field(None, le=100000)

    is_subscription_available: bool = False

    # Per-meal price on a subscription. Omit to use the selling price.
    subscription_price: Optional[Decimal] = Field(None, le=100000)

    # Optional max units of this package per meal slot per day
    daily_capacity: Optional[int] = Field(None, gt=0, le=10000)

    items: List[PackageItemRequest] = Field(..., min_length=1, max_length=50)

    @field_validator("discounted_price", "subscription_price", mode="before")
    @classmethod
    def _zero_none(cls, value):
        return _zero_is_none(value)


class MenuPackageResponse(
    BaseModel
):

    success: bool

    message: str

    package_id: str

    # pending until an Orleeno admin approves the package
    approval_status: Optional[str] = None


class PackageItemResponse(
    BaseModel
):

    item_id: UUID

    item_name: str

    quantity: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class PackageImageResponse(
    BaseModel
):

    image_id: UUID

    image_url: str

    is_primary: bool

    model_config = ConfigDict(from_attributes=True)

class UpdateMenuPackageRequest(
    BaseModel
):

    package_name: Optional[str] = Field(None, min_length=2, max_length=255)

    short_description: Optional[str] = Field(None, max_length=500)

    description: Optional[str] = Field(None, max_length=5000)

    meal_type: Optional[Union[str, List[str]]] = Field(
        None,
        description=(
            "Meal slots — one, any two, or all three. List, comma separated "
            "string, or \"full_day\"."
        )
    )

    food_type: Optional[Union[str, List[str]]] = None

    @field_validator("meal_type", mode="after")
    @classmethod
    def _normalize_meal_type(cls, value):

        if value is None:
            return None

        return normalize_meal_type(value)

    @field_validator("food_type", mode="after")
    @classmethod
    def _normalize_food_type(cls, value):
        if value is None:
            return None
        return normalize_food_type(value)

    price: Optional[Decimal] = Field(None, gt=0, le=100000)

    discounted_price: Optional[Decimal] = Field(None, le=100000)

    is_subscription_available: Optional[bool] = None

    subscription_price: Optional[Decimal] = Field(None, le=100000)

    is_available: Optional[bool] = None

    @field_validator("discounted_price", "subscription_price", mode="before")
    @classmethod
    def _zero_none(cls, value):
        return _zero_is_none(value)

class CommonResponse(
    BaseModel
):

    success: bool

    message: str
