"""Request/response schemas for the customer quote endpoints."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class QuoteCreateRequest(BaseModel):
    beneficiary_id: uuid.UUID
    sender_amount: Decimal


class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote_id: uuid.UUID
    sender_account_id: uuid.UUID
    beneficiary_account_id: uuid.UUID
    sender_amount: Decimal
    sender_currency: str
    token_amount: Decimal
    token_name: str
    sender_transaction_fee: Decimal
    fiat_to_token_exchange_rate: Decimal
    fiat_exchange_rate: Decimal
    exchange_rate_margin: Decimal
    receiver_amount: Decimal
    receiver_currency: str
    receiver_payout_fee: Decimal
    receiver_payout_estimate: Decimal
    created_at: datetime
    expires_at: datetime
    status: str

    @field_serializer("created_at", "expires_at")
    def _as_utc(self, value: datetime) -> str:
        # See models/schemas/integration_message.py for why this is needed:
        # SQLite drops the tz offset Postgres preserves.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()


class QuotePreviewRequest(BaseModel):
    sender_amount: Decimal
    sender_currency: str
    receiver_payout_currency: str


class QuotePreviewRead(BaseModel):
    """A stateless rate preview — no beneficiary, nothing persisted, so no
    quote_id/status/expires_at. See services/quote_service.py's
    RemittancePricing, which this mirrors field-for-field."""

    model_config = ConfigDict(from_attributes=True)

    sender_currency: str
    fiat_to_token_exchange_rate: Decimal
    fiat_exchange_rate: Decimal
    sender_transaction_fee: Decimal
    exchange_rate_margin: Decimal
    token_amount: Decimal
    token_name: str
    receiver_payout_currency: str
    receiver_amount: Decimal
    receiver_payout_fee: Decimal
    receiver_payout_estimate: Decimal
