from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
