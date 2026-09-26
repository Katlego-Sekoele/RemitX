"""Request/response schemas for withdrawal endpoints (customer + admin)."""

import uuid
from decimal import Decimal

from pydantic import ConfigDict

from remitx_api.models.orm.transaction import TransactionStatus
from remitx_api.models.schemas.base import Amount, Schema, UtcDateTime


class WithdrawalCreateRequest(Schema):
    """Request schema for creating a withdrawal."""

    bank_account_id: uuid.UUID
    currency: str
    amount: Amount


class WithdrawalRead(Schema):
    """Response schema for reading a withdrawal."""

    model_config = ConfigDict(from_attributes=True)

    withdrawal_id: uuid.UUID
    tx_id: uuid.UUID
    bank_account_id: uuid.UUID
    status: TransactionStatus
    # Requested amount that leaves the user's RemitX account (fee + net).
    gross_amount: Decimal
    fee_amount: Decimal
    # What actually lands in the user's bank account (gross - fee).
    net_amount: Decimal
    currency: str
    confirmed_by: str | None
    created_at: UtcDateTime
