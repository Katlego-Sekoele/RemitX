"""Request/response schemas for confirming a quote and reading the transfer."""

import uuid
from typing import Literal

from pydantic import ConfigDict, Field

from remitx_api.models.orm.transaction import TransactionStatus
from remitx_api.models.schemas.base import LedgerDecimal, Schema, UtcDateTime


class RemittanceConfirmRequest(Schema):
    quote_id: uuid.UUID

    """A request to confirm a remittance."""


class RemittanceRead(Schema):
    """A read-only representation of a remittance."""

    model_config = ConfigDict(from_attributes=True)

    remittance_id: uuid.UUID
    quote_id: uuid.UUID
    tx_id: uuid.UUID
    status: TransactionStatus
    sender_amount: LedgerDecimal
    sender_currency: str
    token_amount: LedgerDecimal
    token_name: str
    receiver_amount: LedgerDecimal
    receiver_currency: str
    created_at: UtcDateTime


class TransferTimelineStageRead(Schema):
    step: int = Field(ge=1, le=4)
    title: str
    description: str
    occurred_at: UtcDateTime | None


class TransferRead(Schema):
    """One transfer, sent or received, as the caller sees it.

    `status` is the settlement leg's: `pending` (queued), `processing`
    (settling on the XRPL Testnet), `confirmed` or `failed`. `xrpl_tx_hash`
    is the burn transaction's hash, set once the transfer has confirmed.
    """

    model_config = ConfigDict(from_attributes=True)

    remittance_id: uuid.UUID
    quote_id: uuid.UUID
    direction: Literal["sent", "received"]
    counterparty_user_id: uuid.UUID = Field(
        description="The other person. For a sent transfer, the "
        "`linked_user_id` of the beneficiary it went to."
    )
    counterparty_name: str | None = Field(
        description="The other person's verified name: the recipient of a "
        "sent transfer, the sender of a received one."
    )
    status: TransactionStatus
    created_at: UtcDateTime
    processed_at: UtcDateTime | None = Field(
        description="When settlement started on the XRPL Testnet."
    )
    settled_at: UtcDateTime | None = Field(
        description="When the transfer confirmed; null until it has."
    )
    xrpl_tx_hash: str | None
    sender_amount: LedgerDecimal | None = Field(
        description="Null on a received transfer, like the sender's fees."
    )
    sender_currency: str
    sender_transaction_fee: LedgerDecimal | None
    exchange_rate_margin: LedgerDecimal | None
    fiat_to_token_exchange_rate: LedgerDecimal
    fiat_exchange_rate: LedgerDecimal
    token_amount: LedgerDecimal
    token_name: str
    receiver_amount: LedgerDecimal
    receiver_currency: str
    receiver_payout_fee: LedgerDecimal
    receiver_payout_estimate: LedgerDecimal
    timeline_step: int = Field(
        ge=1,
        le=4,
        description="Which stage is active on the settlement timeline.",
    )
    timeline: list[TransferTimelineStageRead]
