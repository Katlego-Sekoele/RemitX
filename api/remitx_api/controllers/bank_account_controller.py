import uuid
from dataclasses import dataclass
from datetime import datetime

from remitx_api.models.orm.bank_account import BankAccount
from remitx_api.services import bank_account_service


# dataclass is used to create immutable view models for bank accounts
@dataclass(frozen=True)
class BankAccountView:
    """View model for a bank account."""

    bank_account_id: uuid.UUID
    account_holder_name: str
    bank_name: str
    account_number: str
    branch_code: str | None
    currency: str
    country: str | None
    status: str
    rejection_reason: str | None
    created_at: datetime


class BankAccountController:
    """Controller for bank account endpoints."""

    def add(
        self,
        user_id: uuid.UUID,
        account_holder_name: str,
        bank_name: str,
        account_number: str,
        currency: str,
        branch_code: str | None,
        country: str | None,
    ) -> BankAccountView:
        """Add a bank account for a user."""
        bank_account = bank_account_service.add_bank_account(
            user_id,
            account_holder_name,
            bank_name,
            account_number,
            currency,
            branch_code=branch_code,
            country=country,
        )
        return self._view(bank_account)

    def list_for_user(
        self, user_id: uuid.UUID, currency: str | None = None
    ) -> list[BankAccountView]:
        """List all bank accounts for a user, regardless of status."""
        return [
            self._view(bank_account)
            for bank_account in bank_account_service.list_user_bank_accounts(
                user_id, currency
            )
        ]

    def list_withdrawable(
        self, user_id: uuid.UUID, currency: str
    ) -> list[BankAccountView]:
        """List all verified bank accounts for a user in a given currency."""
        # Call the service layer to get all withdrawable bank accounts for the
        # user in the specified currency
        return [
            self._view(bank_account)
            for bank_account in bank_account_service.list_withdrawable_bank_accounts(
                user_id, currency
            )
        ]

    def list_pending(self) -> list[BankAccountView]:
        """List all bank accounts that are pending verification."""
        # Call the service layer to get all pending bank accounts
        return [
            self._view(bank_account)
            for bank_account in bank_account_service.list_pending_bank_accounts()
        ]

    def verify(
        self, bank_account_id: uuid.UUID, admin_id: uuid.UUID
    ) -> BankAccountView:
        """Verify a bank account for a user."""
        # Call the service layer to verify the bank account
        bank_account = bank_account_service.verify_bank_account(
            bank_account_id, admin_id
        )
        return self._view(bank_account)

    def reject(
        self, bank_account_id: uuid.UUID, admin_id: uuid.UUID, reason: str
    ) -> BankAccountView:
        """Reject a bank account for a user."""
        # Updates the bank account status and records the rejection reason.
        # Call the service layer to reject the bank account and provide a
        # reason for rejection
        bank_account = bank_account_service.reject_bank_account(
            bank_account_id, admin_id, reason
        )
        return self._view(bank_account)

    def _view(self, bank_account: BankAccount) -> BankAccountView:
        """Private method to convert a bank account ORM model to a
        BankAccountView dataclass."""
        return BankAccountView(
            bank_account_id=bank_account.bank_account_id,
            account_holder_name=bank_account.account_holder_name,
            bank_name=bank_account.bank_name,
            account_number=bank_account.account_number,
            branch_code=bank_account.branch_code,
            currency=bank_account.currency,
            country=bank_account.country,
            status=bank_account.status,
            rejection_reason=bank_account.rejection_reason,
            created_at=bank_account.created_at,
        )
