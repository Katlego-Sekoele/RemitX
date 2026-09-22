import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from remitx_api.models.orm.transaction import Transaction
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository

DIRECTION_IN = "in"
DIRECTION_OUT = "out"


class UnknownAccountError(Exception):
    """`account_id` doesn't exist, or doesn't belong to this caller —
    collapsed into one outcome so a caller can't tell the two apart, same as
    `quote_service.UnknownBeneficiaryError`."""


@dataclass(frozen=True)
class AccountView:
    account_id: uuid.UUID
    currency: str
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
        """Every currency account the caller holds — currently always ZAR +
        uctusd, both created eagerly at signup, but this returns whatever
        `AccountRepository.list_user_accounts` finds rather than assuming
        exactly those two."""
        return [
            AccountView(
                account_id=account.account_id,
                currency=account.account_currency,
                available_balance=self._accounts.get_available_balance(
                    account.account_id
                ),
            )
            for account in self._accounts.list_user_accounts(user_id)
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
