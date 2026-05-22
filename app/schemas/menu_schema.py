from typing import List
from typing import Optional

from pydantic import BaseModel


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