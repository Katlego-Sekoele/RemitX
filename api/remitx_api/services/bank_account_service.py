"""Bank-account CRUD and the admin verification queue: adding one,
listing all, listing withdrawable ones, and verifying/rejecting one."""

import logging
import uuid
from datetime import UTC, datetime
from typing import NoReturn

from remitx_api.extensions import db
from remitx_api.models.orm.bank_account import STATUS_PENDING_VERIFICATION, BankAccount
from remitx_api.repositories.bank_account_repository import BankAccountRepository
from remitx_api.services.exchange_rate_service import SUPPORTED_CURRENCIES

logger = logging.getLogger(__name__)


class BankAccountNotFoundError(Exception):
    """`bank_account_id` doesn't exist, or doesn't belong to this user."""


class BankAccountNotPendingError(Exception):
    """Already verified or rejected — the guarded transition refused."""


class UnsupportedCurrencyError(Exception):
    """Not a fiat currency RemitX pays out in (see SUPPORTED_CURRENCIES)."""


def add_bank_account(
    user_id: uuid.UUID,
    account_holder_name: str,
    bank_name: str,
    account_number: str,
    currency: str,
    branch_code: str | None = None,
    country: str | None = None,
) -> BankAccount:
    """Add a bank account for a user, pending verification."""
    if currency not in SUPPORTED_CURRENCIES:
        logger.warning(
            "bank account refused for user %s: unsupported currency %s",
            user_id,
            currency,
        )
        raise UnsupportedCurrencyError(f"Unsupported currency: {currency}")
    bank_accounts = BankAccountRepository()
    bank_account = bank_accounts.add(
        BankAccount(
            user_id=user_id,
            account_holder_name=account_holder_name,
            bank_name=bank_name,
            account_number=account_number,
            branch_code=branch_code,
            currency=currency,
            country=country,
            # New bank accounts are always pending verification
            status=STATUS_PENDING_VERIFICATION,
        )
    )
    db.session.commit()
    logger.info(
        "bank account %s added for user %s (currency=%s, bank=%s), pending",
        bank_account.bank_account_id,
        user_id,
        currency,
        bank_name,
    )
    return bank_account


def list_user_bank_accounts(
    user_id: uuid.UUID, currency: str | None = None
) -> list[BankAccount]:
    """List all bank accounts for a user, regardless of status."""
    return BankAccountRepository().list_all_user_bank_accounts(user_id, currency)


def list_pending_bank_accounts() -> list[BankAccount]:
    """The admin portal's general-purpose bank account approval queue."""
    return BankAccountRepository().list_pending_bank_account_verification()


def list_withdrawable_bank_accounts(
    user_id: uuid.UUID, currency: str
) -> list[BankAccount]:
    """The users's verified bank accounts in one currency — what the
    withdrawal page's destination picker offers"""
    return BankAccountRepository().list_verified_accounts_by_currency(user_id, currency)


def _raise_not_pending_account(
    bank_accounts: BankAccountRepository,
    bank_account_id: uuid.UUID,
    admin_id: uuid.UUID,
    action: str,
) -> NoReturn:
    """Helper function to raise a BankAccountNotPendingError or
    BankAccountNotFoundError with logging if the bank account is not pending
    or not found."""
    bank_account = bank_accounts.get_by_id(bank_account_id)
    # if the bank account doesn't exist, raise a BankAccountNotFoundError
    if bank_account is None:
        logger.warning(
            "admin %s tried to %s unknown bank_account %s",
            admin_id,
            action,
            bank_account_id,
        )
        raise BankAccountNotFoundError(str(bank_account_id))
    # Else the bank account exists but is not pending, raise a
    # BankAccountNotPendingError
    # Reason it isn't pending should be because its status is either verified
    # or rejected.
    logger.warning(
        "admin %s tried to %s bank_account %s, already %s",
        admin_id,
        action,
        bank_account_id,
        bank_account.status,
    )
    raise BankAccountNotPendingError(str(bank_account_id))


def verify_bank_account(bank_account_id: uuid.UUID, admin_id: uuid.UUID) -> BankAccount:
    """Approve a pending bank account so it can receive withdrawals. The status
    guard lives in the UPDATE itself, so two admins racing can't both win."""
    bank_accounts = BankAccountRepository()
    # if verify returns False, it means no updates were made, which implies the
    # bank account is either not found or not pending.
    if not bank_accounts.verify(bank_account_id, admin_id, datetime.now(UTC)):
        _raise_not_pending_account(bank_accounts, bank_account_id, admin_id, "verify")
    from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
    from remitx_api.services.audit_service import record_audit

    record_audit(
        actor_user_id=admin_id,
        action=AuditAction.CASHOUT_BANK_ACCOUNT_VERIFIED,
        subject_type=AuditSubject.BANK_ACCOUNT,
        subject_id=bank_account_id,
        before={"status": "pending_verification"},
        after={"status": "verified"},
    )
    db.session.commit()
    logger.info("bank account %s verified by admin %s", bank_account_id, admin_id)
    # Return the updated bank account object after verification
    return bank_accounts.get_by_id(bank_account_id)


def reject_bank_account(
    bank_account_id: uuid.UUID, admin_id: uuid.UUID, reason: str
) -> BankAccount:
    """Allow admin to reject a bank account, providing a reason."""
    bank_accounts = BankAccountRepository()
    # if reject returns False, it means no updates were made, which implies the
    # bank account is either not found or not pending.
    if not bank_accounts.reject(bank_account_id, admin_id, reason, datetime.now(UTC)):
        _raise_not_pending_account(bank_accounts, bank_account_id, admin_id, "reject")
    from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
    from remitx_api.services.audit_service import record_audit

    record_audit(
        actor_user_id=admin_id,
        action=AuditAction.CASHOUT_BANK_ACCOUNT_REJECTED,
        subject_type=AuditSubject.BANK_ACCOUNT,
        subject_id=bank_account_id,
        before={"status": "pending_verification"},
        after={"status": "rejected"},
        reason=reason.strip(),
    )
    db.session.commit()
    logger.info(
        "bank account %s rejected by admin %s (%s)", bank_account_id, admin_id, reason
    )
    # Return the updated bank account object after rejection
    return bank_accounts.get_by_id(bank_account_id)
