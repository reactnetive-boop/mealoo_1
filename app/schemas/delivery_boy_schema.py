from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Auth ──────────────────────────────────────────────────

class DeliveryBoyRegisterRequest(BaseModel):
    mobile_number: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=6)


class DeliveryBoyVerifyOTPRequest(BaseModel):
    mobile_number: str
    otp: str = Field(..., min_length=6, max_length=6)


class DeliveryBoyLoginRequest(BaseModel):
    mobile_number: str
    password: str


class DeliveryBoyRegisterResponse(BaseModel):
    success: bool
    contact: str
    message: str
    otp: str  # remove in production — send via SMS


class DeliveryBoyAuthResponse(BaseModel):
    success: bool
    message: str
    delivery_boy_id: Optional[UUID] = None
    is_profile_completed: Optional[bool] = None
    access_token: Optional[str] = None
    token_type: Optional[str] = None


# ── Profile ───────────────────────────────────────────────

class DeliveryBoyProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_boy_id: UUID
    mobile_number: str
    full_name: Optional[str]
    is_mobile_verified: bool
    is_active: bool
    is_online: bool
    vehicle_type: Optional[str]
    vehicle_number: Optional[str]
    profile_image: Optional[str]
    assigned_provider_reference_id: Optional[UUID]
    created_at: Optional[datetime]


class UpdateDeliveryBoyProfileRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=128)
    vehicle_type: Optional[str] = Field(None, description="bike | cycle | scooter | car")
    vehicle_number: Optional[str] = Field(None, max_length=20)
    is_online: Optional[bool] = Field(None, description="Duty status — true when accepting deliveries")


# ── User & Address info (embedded in order detail) ────────

class OrderUserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    full_name: Optional[str]
    phone: Optional[str]


class OrderAddressInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_address_id: UUID
    address_line1: str
    address_line2: Optional[str]
    landmark: Optional[str]
    city: str
    state: str
    pin_code: str
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]


class OrderPackageInfo(BaseModel):
    package_id: UUID
    package_name: str
    quantity: int


class OrderVendorInfo(BaseModel):
    """Pickup-side info: the provider's kitchen the order is collected from."""
    model_config = ConfigDict(from_attributes=True)

    provider_id: UUID
    business_name: Optional[str]
    full_name: Optional[str]
    mobile_number: Optional[str]
    house_no: Optional[str]
    address: Optional[str]
    area: Optional[str]
    landmark: Optional[str]
    city: Optional[str]
    state: Optional[str]
    pincode: Optional[int]


# ── Subscription Orders ───────────────────────────────────

class DeliverySubscriptionOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: UUID
    subscription_reference_id: UUID
    user_reference_id: UUID
    vendor_reference_id: UUID
    order_date: date
    meal_slot: str
    status: str
    is_free_skip: bool
    delivered_at: Optional[datetime]
    delivery_notes: Optional[str]
    created_at: Optional[datetime]


class DeliverySubscriptionOrderListResponse(BaseModel):
    success: bool
    total: int
    orders: List[DeliverySubscriptionOrderResponse]


class DeliverySubscriptionOrderDetailResponse(BaseModel):
    success: bool
    order: DeliverySubscriptionOrderResponse
    user: OrderUserInfo
    delivery_address: OrderAddressInfo
    packages: List[OrderPackageInfo]
    vendor: Optional[OrderVendorInfo] = None


class PickupRequest(BaseModel):
    delivery_notes: Optional[str] = Field(None, max_length=500)


class DeliverRequest(BaseModel):
    otp: str = Field(..., min_length=6, max_length=6, description="OTP received from user")
    delivery_notes: Optional[str] = Field(None, max_length=500)


class OrderActionResponse(BaseModel):
    success: bool
    message: str
    order_id: UUID
    status: str


# ── Extra Orders ──────────────────────────────────────────

class DeliveryExtraOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    extra_order_id: UUID
    user_reference_id: UUID
    vendor_reference_id: UUID
    package_reference_id: UUID
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    delivery_date: date
    meal_slot: str
    status: str
    created_at: Optional[datetime]


class DeliveryExtraOrderListResponse(BaseModel):
    success: bool
    total: int
    orders: List[DeliveryExtraOrderResponse]


class DeliveryExtraOrderDetailResponse(BaseModel):
    success: bool
    order: DeliveryExtraOrderResponse
    user: OrderUserInfo
    delivery_address: OrderAddressInfo
    package_name: str
    vendor: Optional[OrderVendorInfo] = None


# ── Assign delivery boy (provider side) ──────────────────

class AssignDeliveryBoyRequest(BaseModel):
    delivery_boy_id: UUID


# ── Documents ─────────────────────────────────────────────

DOCUMENT_TYPES = ("aadhaar", "pan", "driving_license", "vehicle_rc")


class DeliveryBoyDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_boy_document_id: UUID
    document_type: str
    file_url: str
    status: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class DeliveryBoyDocumentListResponse(BaseModel):
    success: bool
    total: int
    documents: List[DeliveryBoyDocumentResponse]


class DeliveryBoyDocumentUploadResponse(BaseModel):
    success: bool
    message: str
    document: DeliveryBoyDocumentResponse


# ── Payout details ────────────────────────────────────────

class DeliveryBoyPayoutDetailsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_boy_payout_id: UUID
    account_holder_name: Optional[str]
    account_number: Optional[str]
    ifsc_code: Optional[str]
    bank_name: Optional[str]
    upi_id: Optional[str]
    updated_at: Optional[datetime]


class GetPayoutDetailsResponse(BaseModel):
    success: bool
    payout_details: Optional[DeliveryBoyPayoutDetailsResponse] = None


class UpdatePayoutDetailsRequest(BaseModel):
    account_holder_name: Optional[str] = Field(None, max_length=128)
    account_number: Optional[str] = Field(None, max_length=30)
    ifsc_code: Optional[str] = Field(None, max_length=20)
    bank_name: Optional[str] = Field(None, max_length=128)
    upi_id: Optional[str] = Field(None, max_length=128)


class UpdatePayoutDetailsResponse(BaseModel):
    success: bool
    message: str
    payout_details: DeliveryBoyPayoutDetailsResponse


# ── Wallet & earnings ─────────────────────────────────────

class DeliveryBoyWalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_boy_wallet_id: UUID
    balance: Decimal
    total_earned: Decimal
    total_withdrawn: Decimal


class GetWalletResponse(BaseModel):
    success: bool
    wallet: DeliveryBoyWalletResponse


class DeliveryBoyWalletTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_boy_wallet_transaction_id: UUID
    type: str
    reason: str
    amount: Decimal
    balance_after: Decimal
    reference_id: Optional[UUID]
    reference_type: Optional[str]
    description: Optional[str]
    created_at: Optional[datetime]


class WalletTransactionListResponse(BaseModel):
    success: bool
    total: int
    transactions: List[DeliveryBoyWalletTransactionResponse]


class EarningsPeriodSummary(BaseModel):
    deliveries: int
    earnings: Decimal


class EarningsSummaryResponse(BaseModel):
    success: bool
    wallet: DeliveryBoyWalletResponse
    today: EarningsPeriodSummary
    week: EarningsPeriodSummary        # last 7 days including today
    month: EarningsPeriodSummary       # calendar month to date


# ── Notifications ─────────────────────────────────────────

class DeliveryBoyNotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delivery_boy_notification_id: UUID
    type: str
    title: str
    body: str
    data: Optional[dict]
    is_read: bool
    created_at: Optional[datetime]


class NotificationListResponse(BaseModel):
    success: bool
    total: int
    unread: int
    notifications: List[DeliveryBoyNotificationResponse]
