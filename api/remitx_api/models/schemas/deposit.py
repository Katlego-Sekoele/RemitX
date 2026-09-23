"""Request/response schemas for the admin deposit-reconciliation endpoints."""

import uuid
from decimal import Decimal

from remitx_api.models.schemas.base import Schema, UtcDateTime


class DepositRow(Schema):
    """One bank-statement line, as parsed client-side from the uploaded CSV."""

    reference: str | None = None
    amount: Decimal
    date: str | None = None


class ProcessDepositsRequest(Schema):
    rows: list[DepositRow]


class ProcessedDepositRead(Schema):
    deposit_id: uuid.UUID
    reference: str | None
    amount: Decimal
    currency: str
    status: str
    user_id: uuid.UUID | None
    confirmed_by: str | None


class PendingDepositRead(Schema):
    deposit_id: uuid.UUID
    reference: str | None
    amount: Decimal
    currency: str
    created_at: UtcDateTime


class ApproveDepositRequest(Schema):
    """The customer's account reference, for example ``sipho1-zar``.

    Deposits always credit that customer's ZAR account. A reference for one
    of their other currencies still identifies them.
    """

    account_reference: str
