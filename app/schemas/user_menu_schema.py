from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class UserPackageItemResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    item_id: UUID

    # what is in the package; kitchens no longer give units, so none are sent
    item_name: str

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

    # This package's own rating (never mixed with the kitchen's other packages)
    rating_average: Optional[float] = None

    rating_count: int = 0

    # "4.0 (3 reviews)" or "No ratings yet"
    rating_label: str = "No ratings yet"

    # Pincodes the kitchen delivers to (its own + service areas)
    service_pincodes: List[str] = []

    # The kitchen's holidays: regular ones ("Closed every Sunday") and closed
    # dates in the next 30 days ({date, type, label})
    vendor_holidays: Optional[dict] = None


class OfferPackageBrief(BaseModel):

    package_id: UUID

    package_name: str

    provider_id: UUID

    provider_name: Optional[str] = None

    primary_image: Optional[str] = None

    meal_slots: List[str] = []


class StartingPlan(BaseModel):

    subscription_plan_id: UUID

    subscription_type: str

    meal_slot: str

    duration_days: int

    meals: int

    original_amount: Decimal

    discount_percent: Decimal

    discount_amount: Decimal

    final_amount: Decimal

    package: OfferPackageBrief


class OfferSummary(BaseModel):
    """Prices of what is on sale in a pincode (absent when nothing is)."""

    kitchens: int

    packages: int

    lowest_one_time_price: Decimal

    lowest_one_time_package: OfferPackageBrief

    lowest_subscription_meal_price: Optional[Decimal] = None

    lowest_subscription_package: Optional[OfferPackageBrief] = None

    # the best plan discount, taken once off a plan's total
    subscription_discount_percent: Optional[Decimal] = None

    starting_plan: Optional[StartingPlan] = None


class UserPackageListResponse(BaseModel):

    success: bool

    total: int

    serviceable: bool = True

    offer_summary: Optional[OfferSummary] = None

    packages: List[UserPackageListItemResponse]


class PublicPackageReview(BaseModel):

    review_id: UUID

    package_reference_id: Optional[UUID] = None

    vendor_reference_id: UUID

    package_rating: Optional[int] = None

    vendor_rating: int

    review_text: Optional[str] = None

    review_date: Optional[date] = None

    created_at: Optional[datetime] = None


class UserPackageDetailResponse(UserPackageListItemResponse):

    description: Optional[str]

    items: List[UserPackageItemResponse] = []

    images: List[UserPackageImageResponse] = []

    reviews: List[PublicPackageReview] = []

    review_total: int = 0


class ServiceabilityResponse(BaseModel):

    success: bool

    pin_code: int

    serviceable: bool

    # ok | pincode_not_serviceable | no_kitchens
    status: str

    message: Optional[str] = None

    kitchens: int

    packages: int

    offer_summary: Optional[OfferSummary] = None
