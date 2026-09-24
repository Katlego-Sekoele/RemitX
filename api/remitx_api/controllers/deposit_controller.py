import uuid

from remitx_api.models.orm.deposit import Deposit
from remitx_api.models.orm.user import short_display_name
from remitx_api.models.schemas.deposit import (
    ProcessDepositsResponse,
    ProcessedDepositRead,
    SkippedStatementLineRead,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import deposit_service


def _customer_name(
    full_name: str | None, first_name: str | None, last_name: str | None
) -> str | None:
    verified = (full_name or "").strip()
    if verified:
        return verified
    return short_display_name(first_name, last_name)


class DepositController:
    def __init__(self) -> None:
        self._transactions = TransactionRepository()

    def process_deposits(self, rows: list[dict]) -> ProcessDepositsResponse:
        """Run the reconciliation job, then fatten each resulting Deposit
        with its transaction's amount/currency/status — a Deposit row alone
        doesn't carry those, and the admin portal needs them to show what
        happened per statement line.
        """
        result = deposit_service.process_deposits(rows)
        return ProcessDepositsResponse(
            processed=[
                ProcessedDepositRead(**self._fatten(deposit))
                for deposit in result.deposits
            ],
            skipped=[
                SkippedStatementLineRead(
                    reference=line.reference,
                    amount=line.amount,
                    date=line.date,
                    reason=line.reason,
                    message=line.message,
                )
                for line in result.skipped
            ],
        )

    def list_account_references(self) -> list[dict]:
        """Customer account references the statement editor can search."""
        return [
            {
                "reference": reference,
                "currency": currency,
                "name": _customer_name(full_name, first_name, last_name),
            }
            for reference, currency, full_name, first_name, last_name in (
                AccountRepository().list_customer_references()
            )
        ]

    def list_pending(self) -> list[dict]:
        """Pending deposits for the admin portal's manual-review queue."""
        deposits = deposit_service.get_pending_deposits()
        return [self._fatten(deposit) for deposit in deposits]

    def approve(
        self, deposit_id: uuid.UUID, account_reference: str, admin_id: uuid.UUID
    ) -> dict:
        """An admin resolves one pending deposit to the customer who holds
        ``account_reference``, once that person has proven (off-platform)
        that the statement line is theirs. The credit lands on whichever
        account ``account_reference`` identifies (ZAR or token).
        """
        deposit = deposit_service.approve_pending_deposit(
            deposit_id, account_reference, admin_id
        )
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
