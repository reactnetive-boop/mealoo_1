from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WalletRechargeRequest(BaseModel):

    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount to add to wallet (must be positive)"
    )

    description: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional note for this recharge"
    )


class WalletTransactionResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    type: str

    reason: str

    amount: Decimal

    balance_before: Decimal

    balance_after: Decimal

    description: Optional[str]

    created_at: Optional[datetime]


class WalletResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: UUID

    user_id: UUID

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


class WalletTransactionListResponse(BaseModel):

    success: bool

    total: int

    transactions: List[WalletTransactionResponse]
