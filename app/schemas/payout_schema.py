from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PayoutDetailsRequest(BaseModel):
    """Bank account and / or UPI ID that withdrawals are sent to (kitchens and partners)."""

    account_holder_name: Optional[str] = Field(None, min_length=2, max_length=128)
    account_number: Optional[str] = Field(None, pattern=r"^\d{6,18}$")
    ifsc_code: Optional[str] = Field(None, pattern=r"^[A-Za-z]{4}0[A-Za-z0-9]{6}$")
    bank_name: Optional[str] = Field(None, min_length=2, max_length=128)
    upi_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9._-]{2,64}@[A-Za-z0-9.-]{2,64}$")


class CustomerWithdrawalRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, le=100000, max_digits=12, decimal_places=2)
    note: Optional[str] = Field(None, max_length=200)


class TopupOrderRequest(BaseModel):
    amount: Decimal = Field(..., ge=1, le=100000, max_digits=12, decimal_places=2)


class TopupVerifyRequest(BaseModel):
    razorpay_order_id: str = Field(..., max_length=64)
    razorpay_payment_id: str = Field(..., max_length=64)
    razorpay_signature: str = Field(..., max_length=128)
