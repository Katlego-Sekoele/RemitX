"""Request/response schemas for bank-account endpoints (customer + admin)."""

import uuid
from typing import Annotated

from pydantic import ConfigDict, StringConstraints

from remitx_api.models.orm.bank_account import BankAccountStatus
from remitx_api.models.schemas.base import Schema, UtcDateTime

# Required text: whitespace-only counts as blank and is refused with a 422.
NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BankAccountCreateRequest(Schema):
    """Request schema for creating a bank account."""

    account_holder_name: NonBlankStr
    bank_name: NonBlankStr
    account_number: NonBlankStr
    currency: NonBlankStr
    branch_code: str | None = None
    country: str | None = None


class BankAccountRead(Schema):
    """Response schema for reading a bank account.

    `account_number` is masked to its last 4 digits on the customer-facing
    `routes/bank_accounts.py` endpoints, and returned in full on the admin
    ones (`routes/admin/bank_accounts.py`).
    """

    model_config = ConfigDict(from_attributes=True)

    bank_account_id: uuid.UUID
    account_holder_name: str
    bank_name: str
    account_number: str
    branch_code: str | None
    currency: str
    country: str | None
    status: BankAccountStatus
    rejection_reason: str | None
    created_at: UtcDateTime


class RejectBankAccountRequest(Schema):
    """Request schema for rejecting a bank account."""

    reason: str
