"""Request/response schemas for the customer quote endpoints."""

import uuid

from pydantic import ConfigDict, Field

from remitx_api.models.orm.account import PayoutCurrency
from remitx_api.models.schemas.base import Amount, LedgerDecimal, Schema, UtcDateTime


class QuoteCreateRequest(Schema):
    beneficiary_id: uuid.UUID
    sender_amount: Amount
    sender_currency: str
    receiver_payout_currency: PayoutCurrency


class QuoteRead(Schema):
    model_config = ConfigDict(from_attributes=True)

    quote_id: uuid.UUID
    sender_user_id: uuid.UUID
    beneficiary_user_id: uuid.UUID
    sender_amount: LedgerDecimal
    sender_currency: str
    sender_amount_zar: LedgerDecimal = Field(
        description="The send in rand at this quote's rates: what it counts as "
        "against the sending limits, which are in rand from any account."
    )
    token_amount: LedgerDecimal
    token_name: str
    sender_transaction_fee: LedgerDecimal
    fiat_to_token_exchange_rate: LedgerDecimal
    fiat_exchange_rate: LedgerDecimal
    exchange_rate_margin: LedgerDecimal
    receiver_amount: LedgerDecimal
    receiver_currency: str
    receiver_payout_fee: LedgerDecimal
    receiver_payout_estimate: LedgerDecimal
    created_at: UtcDateTime
    expires_at: UtcDateTime
    status: str


class QuotePreviewRequest(Schema):
    sender_amount: Amount
    sender_currency: str
    receiver_payout_currency: PayoutCurrency


class QuotePreviewRead(Schema):
    """A stateless rate preview — no beneficiary, nothing persisted, so no
    quote_id/status/expires_at. See services/quote_service.py's
    RemittancePricing, which this mirrors field-for-field."""

    model_config = ConfigDict(from_attributes=True)

    sender_currency: str
    sender_amount_zar: LedgerDecimal = Field(
        description="The send in rand at these rates, to check against what is "
        "left of the sending limits. The quote locks its own."
    )
    fiat_to_token_exchange_rate: LedgerDecimal
    fiat_exchange_rate: LedgerDecimal
    sender_transaction_fee: LedgerDecimal
    exchange_rate_margin: LedgerDecimal
    token_amount: LedgerDecimal
    token_name: str
    receiver_payout_currency: str
    receiver_amount: LedgerDecimal
    receiver_payout_fee: LedgerDecimal
    receiver_payout_estimate: LedgerDecimal
