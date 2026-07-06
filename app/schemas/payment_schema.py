from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InitiatePaymentRequest(BaseModel):

    amount: Decimal = Field(..., gt=0, description="Amount to add to wallet (must be positive)")


class InitiatePaymentResponse(BaseModel):

    success: bool
    message: str
    payment_id: UUID
    gateway_order_id: str
    amount: Decimal


class ConfirmPaymentRequest(BaseModel):

    gateway_txn_id: str = Field(
        ...,
        description="Transaction ID returned by the (mock) payment gateway after the user pays"
    )


class ConfirmPaymentResponse(BaseModel):

    success: bool
    message: str
    balance_before: Decimal
    amount_added: Decimal
    balance_after: Decimal


class PaymentResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    payment_id: UUID
    user_reference_id: UUID
    subscription_reference_id: Optional[UUID]
    extra_order_reference_id: Optional[UUID]
    purpose: str
    amount: Decimal
    currency: Optional[str]
    method: str
    status: str
    gateway: Optional[str]
    gateway_order_id: Optional[str]
    gateway_txn_id: Optional[str]
    paid_at: Optional[datetime]
    refunded_at: Optional[datetime]
    refund_amount: Optional[Decimal]
    failure_reason: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class PaymentListResponse(BaseModel):

    success: bool
    total: int
    payments: List[PaymentResponse]


class RefundPaymentRequest(BaseModel):

    refund_amount: Optional[Decimal] = Field(
        None,
        gt=0,
        description="Amount to refund; defaults to the full payment amount if omitted"
    )

    reason: Optional[str] = Field(None, max_length=255)
