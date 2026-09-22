"""Request/response schemas for the customer account endpoints."""

import uuid
from decimal import Decimal

from remitx_api.models.schemas.base import Schema, UtcDateTime


class AccountRead(Schema):
    """A read-only representation of a customer currency account.
    Can be used to display the account's current balance and currency."""

    account_id: uuid.UUID
    currency: str
    available_balance: Decimal


class AccountTransactionRead(Schema):
    """A read-only representation of a transaction on a customer currency account."""

    tx_id: uuid.UUID
    type: str
    direction: str
    amount: Decimal
    currency: str
    status: str
    created_at: UtcDateTime
    confirmed_at: UtcDateTime | None
