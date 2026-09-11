"""Request/response schemas for the admin deposit-reconciliation endpoints."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, field_serializer


class DepositRow(BaseModel):
    """One bank-statement line, as parsed client-side from the uploaded CSV."""

    reference: str | None = None
    amount: Decimal
    date: str | None = None


class ProcessDepositsRequest(BaseModel):
    rows: list[DepositRow]


class ProcessedDepositRead(BaseModel):
    deposit_id: uuid.UUID
    reference: str | None
    amount: Decimal
    currency: str
    status: str
    user_id: uuid.UUID | None
    confirmed_by: str | None


class PendingDepositRead(BaseModel):
    deposit_id: uuid.UUID
    reference: str | None
    amount: Decimal
    currency: str
    created_at: datetime

    @field_serializer("created_at")
    def _as_utc(self, value: datetime) -> str:
        # See models/schemas/integration_message.py for why this is needed:
        # SQLite drops the tz offset Postgres preserves.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()


class ApproveDepositRequest(BaseModel):
    user_id: uuid.UUID
