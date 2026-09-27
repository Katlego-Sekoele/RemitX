"""Request/response schemas for the account endpoints: a customer's own, and
RemitX's platform accounts for treasury staff."""

import uuid
from typing import Literal

from remitx_api.models.orm.account import PayoutCurrency
from remitx_api.models.orm.transaction import TransactionStatus
from remitx_api.models.schemas.base import LedgerDecimal, Schema, UtcDateTime


class AccountOpenRequest(Schema):
    """A fiat payout currency the caller does not hold yet."""

    currency: PayoutCurrency


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
    balance: LedgerDecimal
    # `balance` less this account's in-flight outgoing legs, 2 dp. The
    # difference is what's still pending.
    available_balance: LedgerDecimal


class PlatformAccountRead(Schema):
    """One of RemitX's own accounts, or an external counterparty it settles
    against. None has a reference: they are known by `label`."""

    account_id: uuid.UUID
    # e.g. "RemitX SA Bank Account", "RemitX XRPL Treasury Wallet".
    label: str
    # REMITX_FIAT: RemitX's bank account in one settlement country.
    # REMITX_REVENUE: the fees it has earned in that currency.
    # REMITX_XRPL_WALLET: the treasury wallet every transfer settles through.
    # EXTERNAL: a counterparty RemitX doesn't hold, e.g. the uctusd issuer.
    type: Literal["REMITX_FIAT", "REMITX_REVENUE", "REMITX_XRPL_WALLET", "EXTERNAL"]
    currency: str
    # `settlement` for the uctusd (RLUSD) accounts, `fiat` for everything else.
    kind: Literal["fiat", "settlement"]
    # The ledger balance, 2 dp. Negative for the issuer, which has paid out
    # what the treasury wallet holds.
    balance: LedgerDecimal
    # `balance` less this account's in-flight outgoing legs, 2 dp.
    available_balance: LedgerDecimal


class TreasuryCoverageRead(Schema):
    """Token the treasury wallet can still spend, and token customers hold."""

    token_available: LedgerDecimal
    customer_token_balances: LedgerDecimal


class AccountTransactionRead(Schema):
    """A read-only representation of a transaction on a customer currency account."""

    tx_id: uuid.UUID
    type: str
    direction: str
    amount: LedgerDecimal
    currency: str
    status: TransactionStatus
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
