from typing import List, Optional, Literal
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Auth ──────────────────────────────────────────────────

MOBILE_PATTERN = r"^[6-9]\d{9}$"


class DeliveryBoyRegisterRequest(BaseModel):
    mobile_number: str = Field(..., pattern=MOBILE_PATTERN)
    password: str = Field(..., min_length=8, max_length=64)


class DeliveryBoyVerifyOTPRequest(BaseModel):
    mobile_number: str = Field(..., pattern=MOBILE_PATTERN)
    otp: str = Field(..., pattern=r"^\d{6}$")


class DeliveryBoyLoginRequest(BaseModel):
    mobile_number: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=1, max_length=64)


class DeliveryBoyForgotPasswordRequest(BaseModel):
    mobile_number: str = Field(..., pattern=MOBILE_PATTERN)


class DeliveryBoyResetPasswordRequest(BaseModel):
    mobile_number: str = Field(..., pattern=MOBILE_PATTERN)
    reset_token: str = Field(..., min_length=20, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=64)
    confirm_password: str = Field(..., min_length=8, max_length=64)


class DeliveryBoyRegisterResponse(BaseModel):
    success: bool
    contact: str
    message: str
    otp: Optional[str] = None  # only outside production (no SMS gateway yet)


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
    email: Optional[str]
    date_of_birth: Optional[date]
    gender: Optional[str]
    is_mobile_verified: bool
    is_active: bool
    is_online: bool
    vehicle_type: Optional[str]
    vehicle_number: Optional[str]
    profile_image: Optional[str]
    assigned_provider_reference_id: Optional[UUID]
    approval_status: str = "pending"
    approval_note: Optional[str] = None
    created_at: Optional[datetime]


class UpdateDeliveryBoyProfileRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=128)
    email: Optional[str] = Field(None, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    date_of_birth: Optional[date] = Field(None, description="YYYY-MM-DD")
    gender: Optional[Literal["male", "female", "other"]] = None
    vehicle_type: Optional[Literal["bike", "cycle", "scooter", "car"]] = None
    vehicle_number: Optional[str] = Field(None, min_length=4, max_length=20, pattern=r"^[A-Za-z0-9 -]+$")
    is_online: Optional[bool] = Field(None, description="Duty status: only online partners can be assigned deliveries")


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
    picked_up_at: Optional[datetime] = None
    delivery_notes: Optional[str]
    # True after too many wrong customer codes; admin must resolve
    delivery_locked: bool = False
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
    # 4-digit code shown to the kitchen on the order; proves the hand-over
    pickup_code: str = Field(..., pattern=r"^\d{4}$")
    delivery_notes: Optional[str] = Field(None, max_length=500)


class DeliverRequest(BaseModel):
    # 6-digit code the customer reads out at the door
    otp: str = Field(..., pattern=r"^\d{6}$", description="Delivery code from the customer")
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
    delivered_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    delivery_locked: bool = False
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
    # Private file: fetch through GET /delivery/documents/{id}/file
    file_url: Optional[str] = None
    status: str
    remarks: Optional[str] = None
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
    account_holder_name: Optional[str] = Field(None, min_length=2, max_length=128)
    account_number: Optional[str] = Field(None, pattern=r"^\d{6,18}$")
    ifsc_code: Optional[str] = Field(None, pattern=r"^[A-Za-z]{4}0[A-Za-z0-9]{6}$")
    bank_name: Optional[str] = Field(None, min_length=2, max_length=128)
    upi_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9._-]{2,64}@[A-Za-z0-9.-]{2,64}$")


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


class DeliveryWithdrawalRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, le=1000000, max_digits=12, decimal_places=2)
    note: Optional[str] = Field(None, max_length=255)
