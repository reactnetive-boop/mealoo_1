from typing import List
from typing import Optional
from typing import Union

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from uuid import UUID

from app.utils.meal_type import normalize_meal_type

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

    category_id: UUID = Field(
        ...,
        description="category_id from GET /menu/categories"
    )

    package_name: str

    short_description: Optional[str] = None

    description: Optional[str] = None

    meal_type: Union[str, List[str]] = Field(
        ...,
        description=(
            "Meal slots this package is served in — one, any two, or all three. "
            "Send a list ([\"lunch\", \"dinner\"]), a comma separated string "
            "(\"lunch, dinner\") or \"full_day\" for all three. "
            "Stored as \"breakfast,lunch,dinner\" order."
        ),
        examples=[["lunch", "dinner"]]
    )

    food_type: str = Field(
        ...,
        description="veg | non_veg | egg"
    )

    @field_validator("meal_type", mode="after")
    @classmethod
    def _normalize_meal_type(cls, value):

        return normalize_meal_type(value)

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

    meal_type: Optional[Union[str, List[str]]] = Field(
        None,
        description=(
            "Meal slots — one, any two, or all three. List, comma separated "
            "string, or \"full_day\"."
        )
    )

    food_type: Optional[str] = None

    @field_validator("meal_type", mode="after")
    @classmethod
    def _normalize_meal_type(cls, value):

        if value is None:
            return None

        return normalize_meal_type(value)

    price: Optional[float] = None

    discounted_price: Optional[float] = None

    is_subscription_available: Optional[bool] = None

    subscription_price: Optional[float] = None

class CommonResponse(
    BaseModel
):

    success: bool

    message: str
