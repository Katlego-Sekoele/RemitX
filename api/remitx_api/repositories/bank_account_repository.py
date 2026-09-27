import uuid
from datetime import datetime

from sqlalchemy import func, select, update

from remitx_api.extensions import db
from remitx_api.models.orm.bank_account import (
    STATUS_PENDING_VERIFICATION,
    STATUS_REJECTED,
    STATUS_VERIFIED,
    BankAccount,
)
from remitx_api.repositories.repository import Repository


class BankAccountRepository(Repository[BankAccount, uuid.UUID]):
    """Repository for BankAccount ORM objects."""

    def __init__(self) -> None:
        super().__init__(BankAccount)

    def add(self, bank_account: BankAccount) -> BankAccount:
        """Insert a bank account. Flushes only — caller commits."""
        db.session.add(bank_account)
        db.session.flush()
        return bank_account

    def list_all_user_bank_accounts(
        self, user_id: uuid.UUID, currency: str | None = None
    ) -> list[BankAccount]:
        """Every one of the user_id's bank accounts, any status — the
        currency-account detail view, so a user can see a `pending` or
        `rejected` account they adde.
        `currency` is an optional parameter to show accounts for a specific
        currency. If unset, function returns accounts across every currency.
        potential use: display accounts in a general "manage my bank accounts" page."""
        query = select(BankAccount).where(BankAccount.user_id == user_id)
        if currency is not None:  # if currency is provided, filter by it
            query = query.where(BankAccount.currency == currency)
        return db.session.scalars(query.order_by(BankAccount.created_at.desc())).all()

    def list_verified_accounts_by_currency(
        self, user_id: uuid.UUID, currency: str
    ) -> list[BankAccount]:
        """The caller's own verified bank accounts in one currency — can be used in
        the withdrawal page's destination picker, so the page only ever offers an
        account that can actually settle immediately."""
        return db.session.scalars(
            select(BankAccount)
            .where(
                BankAccount.user_id == user_id,
                BankAccount.currency == currency,
                BankAccount.status == STATUS_VERIFIED,
            )
            .order_by(BankAccount.created_at.desc())
        ).all()

    def list_pending_bank_account_verification(self) -> list[BankAccount]:
        """Return all bank accounts that are pending verification.
        potential use: admin page to show all accounts that need verification."""
        return db.session.scalars(
            select(BankAccount)
            .where(BankAccount.status == STATUS_PENDING_VERIFICATION)
            .order_by(BankAccount.created_at)
        ).all()

    def count_pending_verification(self) -> int:
        """How many bank accounts are waiting on a reviewer."""
        count = db.session.scalar(
            select(func.count(BankAccount.bank_account_id)).where(
                BankAccount.status == STATUS_PENDING_VERIFICATION
            )
        )
        return int(count or 0)

    def verify(
        self, bank_account_id: uuid.UUID, admin_id: uuid.UUID, verified_at: datetime
    ) -> bool:
        """Guarded pending_verification -> verified. Flushes only — caller
        commits. Returns True iff a row changed."""
        return self._transition_from_pending(
            bank_account_id,
            status=STATUS_VERIFIED,
            verified_by_admin_id=admin_id,
            verified_at=verified_at,
        )

    def reject(
        self,
        bank_account_id: uuid.UUID,
        admin_id: uuid.UUID,
        reason: str,
        rejected_at: datetime,
    ) -> bool:
        """Guarded pending_verification -> rejected. Flushes only — caller
        commits. Returns True iff a row changed."""
        return self._transition_from_pending(
            bank_account_id,
            status=STATUS_REJECTED,
            verified_by_admin_id=admin_id,
            verified_at=rejected_at,
            rejection_reason=reason,
        )

    def _transition_from_pending(self, bank_account_id: uuid.UUID, **values) -> bool:
        """Helper method to update a bank account's status from pending verification to
        either verified or rejected. Returns True if the update was successful
        (i.e., a row was updated), otherwise returns False."""
        result = db.session.execute(
            update(BankAccount)
            .where(
                BankAccount.bank_account_id == bank_account_id,
                BankAccount.status == STATUS_PENDING_VERIFICATION,
            )
            .values(**values)
        )
        db.session.flush()
        return result.rowcount == 1
