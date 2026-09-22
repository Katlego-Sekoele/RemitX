"""Request/response schemas for the customer account endpoints."""

import uuid
from decimal import Decimal
from typing import Literal

from remitx_api.models.schemas.base import Schema, UtcDateTime


class AccountRead(Schema):
    """A read-only representation of a customer currency account.
    Can be used to display the account's current balance and currency."""

    account_id: uuid.UUID
    currency: str
    # The permanent reference, e.g. "sipho1-zar": what to quote on an EFT
    # into the ZAR account, and what to share with a sender.
    reference: str
    # `settlement` for the uctusd (RLUSD) wallet, `fiat` for everything else.
    kind: Literal["fiat", "settlement"]
    # The ledger balance, 2 dp.
    balance: Decimal
    # `balance` less this account's in-flight outgoing legs, 2 dp. The
    # difference is what's still pending.
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
    # Plain language, from the account owner's side: "Deposit",
    # "Transfer fee", "Sent to Tendai M.", "Received from Sipho K.",
    # "Converted to ZWL".
    description: str
    # The other customer, on the legs of a transfer.
    counterparty_name: str | None
    # The transfer this leg belongs to, if any.
    remittance_id: uuid.UUID | None
    # The transfer's XRPL Testnet burn hash, on every leg of a confirmed
    # transfer.
    xrpl_tx_hash: str | None
