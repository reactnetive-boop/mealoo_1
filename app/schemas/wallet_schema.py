from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WalletRechargeRequest(BaseModel):

    amount: Decimal = Field(
        ...,
        gt=0,
        max_digits=10,
        decimal_places=2,
        description="Amount to add to wallet (positive, up to 2 decimals)"
    )

    description: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional note for this recharge"
    )


class WalletTransactionResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    wallet_transaction_id: UUID

    type: str

    reason: str

    amount: Decimal

    balance_before: Decimal

    balance_after: Decimal

    reference_type: Optional[str] = None

    reference_id: Optional[UUID] = None

    description: Optional[str]

    created_at: Optional[datetime]


class WalletResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    # None until the first credit creates the wallet row
    wallet_id: Optional[UUID] = None

    user_reference_id: UUID

    balance: Decimal

    created_at: Optional[datetime]

    updated_at: Optional[datetime]


class WalletDetailsResponse(BaseModel):

    success: bool

    wallet: WalletResponse

    transactions: List[WalletTransactionResponse]


class WalletRechargeResponse(BaseModel):

    success: bool

    message: str

    balance_before: Decimal

    amount_added: Decimal

    balance_after: Decimal

    payment_id: Optional[UUID] = None


class WalletTransactionListResponse(BaseModel):

    success: bool

    total: int

    transactions: List[WalletTransactionResponse]
