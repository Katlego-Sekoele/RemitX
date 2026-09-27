"""Request/response schemas for withdrawal endpoints (customer + admin)."""

import uuid

from pydantic import ConfigDict

from remitx_api.models.orm.transaction import TransactionStatus
from remitx_api.models.schemas.base import Amount, LedgerDecimal, Schema, UtcDateTime


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
    gross_amount: LedgerDecimal
    fee_amount: LedgerDecimal
    # What actually lands in the user's bank account (gross - fee).
    net_amount: LedgerDecimal
    currency: str
    confirmed_by: str | None
    created_at: UtcDateTime
