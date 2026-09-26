"""Request/response schemas for the admin deposit-reconciliation endpoints."""

import uuid
from decimal import Decimal
from enum import StrEnum

from remitx_api.models.schemas.base import Schema, UtcDateTime


class DepositRow(Schema):
    """One bank-statement line, as parsed client-side from the uploaded CSV.

    ``currency`` is that of the RemitX bank account the money came into: ZAR,
    USD, ZWL or NAD. A line without one RemitX banks in is skipped.
    Optional ``line_id`` is the bank export's stable line identifier when
    present.
    """

    reference: str | None = None
    amount: Decimal
    currency: str | None = None
    date: str | None = None
    line_id: str | None = None


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


class SkippedStatementLineReason(StrEnum):
    """Why a statement line produced no deposit on this run."""

    UNPARSEABLE_DATE = "unparseable_date"
    UNKNOWN_CURRENCY = "unknown_currency"
    NOT_INCOMING = "not_incoming"
    ALREADY_RECONCILED = "already_reconciled"


class SkippedStatementLineRead(Schema):
    reference: str | None
    amount: Decimal
    date: str | None
    reason: SkippedStatementLineReason
    message: str


class ProcessDepositsResponse(Schema):
    processed: list[ProcessedDepositRead]
    skipped: list[SkippedStatementLineRead]


class PendingDepositRead(Schema):
    deposit_id: uuid.UUID
    reference: str | None
    amount: Decimal
    currency: str
    created_at: UtcDateTime


class AccountReferenceRead(Schema):
    """One customer account a statement line can match.

    ``name`` is a display name, never an email.
    """

    reference: str
    currency: str
    name: str | None = None


class ApproveDepositRequest(Schema):
    """The customer's account reference, for example ``sipho1-zar``.

    It must name an account in the deposit's currency: a ZAR deposit lands
    on a ZAR account, never on a USD or token one.
    """

    account_reference: str
