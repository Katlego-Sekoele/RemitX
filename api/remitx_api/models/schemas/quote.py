"""Request/response schemas for the customer quote endpoints."""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, computed_field, field_serializer

# The inverted rate is for reading only, so it's rounded to the 4 dp people
# see: 1 / 0.05405405 is 18.50000139, not the 18.50 it was inverted from.
DISPLAY_RATE_QUANTUM = Decimal("0.0001")


def _token_to_fiat(fiat_to_token_exchange_rate: Decimal) -> Decimal:
    """Sender currency per token unit (18.5000 rand per RLUSD), the way people
    read the rate. Pricing keeps it the other way round, at full precision."""
    return (Decimal("1") / fiat_to_token_exchange_rate).quantize(
        DISPLAY_RATE_QUANTUM, rounding=ROUND_HALF_UP
    )


class QuoteCreateRequest(BaseModel):
    beneficiary_id: uuid.UUID
    sender_amount: Decimal
    sender_currency: str
    receiver_payout_currency: str


class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quote_id: uuid.UUID
    sender_user_id: uuid.UUID
    beneficiary_user_id: uuid.UUID
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
    RemittancePricing, which this mirrors field-for-field, plus the rate
    the other way round for display."""

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

    @computed_field
    @property
    def token_to_fiat_exchange_rate(self) -> Decimal:
        return _token_to_fiat(self.fiat_to_token_exchange_rate)
