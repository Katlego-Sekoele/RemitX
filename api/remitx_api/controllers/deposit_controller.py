import uuid

from remitx_api.models.orm.deposit import Deposit
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import deposit_service


class DepositController:
    def __init__(self) -> None:
        self._transactions = TransactionRepository()

    def process_deposits(self, rows: list[dict]) -> list[dict]:
        """Run the reconciliation job, then fatten each resulting Deposit
        with its transaction's amount/currency/status — a Deposit row alone
        doesn't carry those, and the admin portal needs them to show what
        happened per statement line.
        """
        deposits = deposit_service.process_deposits(rows)
        return [self._fatten(deposit) for deposit in deposits]

    def list_pending(self) -> list[dict]:
        """Pending deposits for the admin portal's manual-review queue."""
        deposits = deposit_service.get_pending_deposits()
        return [self._fatten(deposit) for deposit in deposits]

    def approve(
        self, deposit_id: uuid.UUID, user_id: uuid.UUID, admin_id: uuid.UUID
    ) -> dict:
        """An admin resolves one pending deposit to a user, once that user has
        proven (off-platform — email/SMS) that a statement line is theirs.
        """
        deposit = deposit_service.approve_pending_deposit(deposit_id, user_id, admin_id)
        return self._fatten(deposit)

    def _fatten(self, deposit: Deposit) -> dict:
        transaction = self._transactions.get_by_id(deposit.tx_id)
        return {
            "deposit_id": deposit.deposit_id,
            "reference": deposit.user_account_reference,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "status": transaction.status,
            "user_id": deposit.user_id,
            "confirmed_by": deposit.confirmed_by,
            "created_at": transaction.created_at,
        }
