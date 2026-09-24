"""Request/response schemas for the customer quote endpoints."""

import uuid
from decimal import Decimal

from pydantic import ConfigDict

from remitx_api.models.orm.account import PayoutCurrency
from remitx_api.models.schemas.base import Schema, UtcDateTime


class QuoteCreateRequest(Schema):
    beneficiary_id: uuid.UUID
    sender_amount: Decimal
    sender_currency: str
    receiver_payout_currency: PayoutCurrency


class QuoteRead(Schema):
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
    created_at: UtcDateTime
    expires_at: UtcDateTime
    status: str


class QuotePreviewRequest(Schema):
    sender_amount: Decimal
    sender_currency: str
    receiver_payout_currency: PayoutCurrency


class QuotePreviewRead(Schema):
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
