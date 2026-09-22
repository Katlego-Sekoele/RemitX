import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from remitx_api.models.orm.account import CURRENCY_TOKEN, CURRENCY_ZAR, Account
from remitx_api.models.orm.transaction import Transaction
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository

DIRECTION_IN = "in"
DIRECTION_OUT = "out"

# What an account is for, so a client can tell the settlement token's wallet
# apart from a spendable currency account without hard-coding the token name.
KIND_FIAT = "fiat"
KIND_SETTLEMENT = "settlement"

# Amounts leave the API at 2 dp, the same quantum quote_service stores them at.
AMOUNT_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def account_kind(currency: str) -> str:
    return KIND_SETTLEMENT if currency == CURRENCY_TOKEN else KIND_FIAT


def _display_order(account: Account) -> tuple[int, str]:
    """ZAR first, then the other fiat currencies alphabetically, then the
    settlement token's wallet last."""
    if account.account_currency == CURRENCY_ZAR:
        return (0, "")
    if account.account_currency == CURRENCY_TOKEN:
        return (2, "")
    return (1, account.account_currency)


class UnknownAccountError(Exception):
    """`account_id` doesn't exist, or doesn't belong to this caller —
    collapsed into one outcome so a caller can't tell the two apart, same as
    `quote_service.UnknownBeneficiaryError`."""


@dataclass(frozen=True)
class AccountView:
    account_id: uuid.UUID
    currency: str
    reference: str
    kind: str
    # The ledger balance. `available_balance` nets out this account's own
    # in-flight outgoing legs, so the difference is what's still pending.
    balance: Decimal
    available_balance: Decimal


@dataclass(frozen=True)
class AccountTransactionView:
    tx_id: uuid.UUID
    type: str
    direction: str
    amount: Decimal
    currency: str
    status: str
    created_at: datetime
    confirmed_at: datetime | None


class AccountController:
    def __init__(self) -> None:
        self._accounts = AccountRepository()
        self._transactions = TransactionRepository()

    def get_accounts(self, user_id: uuid.UUID) -> list[AccountView]:
        """Every currency account the caller holds: ZAR and uctusd from
        signup, plus any payout currency received since. Returns whatever
        `AccountRepository.list_user_accounts` finds rather than assuming
        exactly those, in display order (see `_display_order`)."""
        accounts = sorted(
            self._accounts.list_user_accounts(user_id), key=_display_order
        )
        return [
            AccountView(
                account_id=account.account_id,
                currency=account.account_currency,
                reference=account.reference,
                kind=account_kind(account.account_currency),
                balance=_money(account.account_balance),
                available_balance=_money(
                    self._accounts.get_available_balance(account.account_id)
                ),
            )
            for account in accounts
        ]

    def get_account_history(
        self, user_id: uuid.UUID, account_id: uuid.UUID
    ) -> list[AccountTransactionView]:
        account = self._accounts.get_by_id(account_id)
        if account is None or account.user_id != user_id:
            raise UnknownAccountError(str(account_id))

        return [
            self._leg_view(leg, account_id)
            for leg in self._transactions.list_account_transactions(account_id)
        ]

    def _leg_view(
        self, leg: Transaction, account_id: uuid.UUID
    ) -> AccountTransactionView:
        # credit=source, debit=destination (models/orm/transaction.py) — this
        # account received the money iff it's the leg's debit side.
        direction = (
            DIRECTION_IN if leg.debit_account_id == account_id else DIRECTION_OUT
        )
        return AccountTransactionView(
            tx_id=leg.tx_id,
            type=leg.type,
            direction=direction,
            amount=leg.amount,
            currency=leg.currency,
            status=leg.status,
            created_at=leg.created_at,
            confirmed_at=leg.confirmed_at,
        )
