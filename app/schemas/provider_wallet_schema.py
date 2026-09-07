from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderWalletTransactionResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    provider_wallet_transaction_id: UUID
    type: str
    reason: str
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    reference_id: Optional[UUID]
    reference_type: Optional[str]
    description: Optional[str]
    created_at: Optional[datetime]


class ProviderWalletResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    provider_wallet_id: UUID
    provider_reference_id: UUID
    balance: Decimal
    total_earned: Decimal
    total_withdrawn: Decimal
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class ProviderWalletDetailsResponse(BaseModel):

    success: bool
    wallet: ProviderWalletResponse
    recent_transactions: List[ProviderWalletTransactionResponse]


class ProviderWalletTransactionListResponse(BaseModel):

    success: bool
    total: int
    transactions: List[ProviderWalletTransactionResponse]


class WithdrawalRequest(BaseModel):

    amount: Decimal = Field(
        ...,
        gt=0,
        description="Amount to withdraw (must be positive and <= current balance)"
    )

    description: Optional[str] = Field(
        None,
        max_length=255
    )


class WithdrawalResponse(BaseModel):

    success: bool
    message: str
    balance_before: Decimal
    amount_withdrawn: Decimal
    balance_after: Decimal
