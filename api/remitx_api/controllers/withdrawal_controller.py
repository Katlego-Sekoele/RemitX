import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from remitx_api.models.orm.transaction import Transaction
from remitx_api.models.orm.withdrawal import Withdrawal
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import withdrawal_service


# dataclass is used to create immutable view models for withdrawals
@dataclass(frozen=True)
class WithdrawalView:
    """View model for a withdrawal."""

    withdrawal_id: uuid.UUID
    tx_id: uuid.UUID
    bank_account_id: uuid.UUID
    status: str
    gross_amount: Decimal
    fee_amount: Decimal
    net_amount: Decimal
    currency: str
    confirmed_by: str | None
    created_at: datetime


class WithdrawalController:
    """Controller for withdrawal endpoints."""

    def __init__(self) -> None:
        self._transactions = TransactionRepository()

    def request(
        self,
        user_id: uuid.UUID,
        bank_account_id: uuid.UUID,
        currency: str,
        amount: Decimal,
    ) -> WithdrawalView:
        """Request a withdrawal for a user to a specific bank account."""
        withdrawal = withdrawal_service.request_withdrawal(
            user_id, bank_account_id, currency, amount
        )
        return self._view(withdrawal, self._transactions.get_by_id(withdrawal.tx_id))

    def list_user_withdrawal_history(self, user_id: uuid.UUID) -> list[WithdrawalView]:
        """A user's own withdrawal history"""
        # Call the service layer to get all withdrawals for the users
        return [
            self._view(withdrawal, transaction)
            for withdrawal, transaction in withdrawal_service.list_user_withdrawals(
                user_id
            )
        ]

    def _view(self, withdrawal: Withdrawal, transaction: Transaction) -> WithdrawalView:
        """Private method to convert a withdrawal ORM model, plus its linked
        withdrawal transaction (which holds the status), to a WithdrawalView
        dataclass."""
        return WithdrawalView(
            withdrawal_id=withdrawal.withdrawal_id,
            tx_id=withdrawal.tx_id,
            bank_account_id=withdrawal.bank_account_id,
            status=transaction.status,
            gross_amount=withdrawal.gross_amount,
            fee_amount=withdrawal.fee_amount,
            net_amount=withdrawal.net_amount,
            currency=withdrawal.currency,
            confirmed_by=withdrawal.confirmed_by,
            created_at=withdrawal.created_at,
        )
