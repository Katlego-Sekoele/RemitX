import uuid
from datetime import datetime

from sqlalchemy import or_, select, update

from remitx_api.extensions import db
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    Transaction,
)
from remitx_api.repositories.repository import Repository


class TransactionRepository(Repository[Transaction, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(Transaction)

    def add(self, transaction: Transaction) -> Transaction:
        """Insert a transaction. Flushes only — caller commits."""
        db.session.add(transaction)
        db.session.flush()
        return transaction

    def get_by_transaction_type_and_debit_account(
        self, type: str, debit_account_id: uuid.UUID
    ) -> Transaction | None:
        """First transaction of `type` crediting into `debit_account_id`, if
        any. Used for one-off idempotency checks (e.g. "has the treasury's
        pre-funded balance already been recorded?") rather than a per-request
        lookup.
        """
        return db.session.scalars(
            select(Transaction).where(
                Transaction.type == type,
                Transaction.debit_account_id == debit_account_id,
            )
        ).first()

    def get_pending_transactions(self) -> list[Transaction]:
        """Every transaction still `pending`, oldest first."""
        return db.session.scalars(
            select(Transaction)
            .where(Transaction.status == STATUS_PENDING)
            .order_by(Transaction.created_at)
        ).all()

    def list_account_transactions(self, account_id: uuid.UUID) -> list[Transaction]:
        """Every leg touching this account, either side, newest first — an
        account's transaction history. `credit`=source, `debit`=destination
        (models/orm/transaction.py), so an account can appear on either side
        depending on the leg."""
        return db.session.scalars(
            select(Transaction)
            .where(
                or_(
                    Transaction.credit_account_id == account_id,
                    Transaction.debit_account_id == account_id,
                )
            )
            .order_by(Transaction.created_at.desc())
        ).all()

    def confirm_pending_deposit_transaction(
        self,
        tx_id: uuid.UUID,
        debit_account_id: uuid.UUID,
        confirmed_at: datetime,
    ) -> bool:
        """Fill in a pending row's destination account and confirm it.

        Guarded on status='pending', so two admins resolving the same
        unmatched deposit can't both succeed. Returns True iff a row changed.
        """
        result = db.session.execute(
            update(Transaction)
            .where(Transaction.tx_id == tx_id, Transaction.status == STATUS_PENDING)
            .values(
                debit_account_id=debit_account_id,
                status=STATUS_CONFIRMED,
                confirmed_at=confirmed_at,
            )
        )
        return result.rowcount == 1

    def confirm_pending_transaction(
        self, tx_id: uuid.UUID, confirmed_at: datetime
    ) -> bool:
        """Guarded pending -> confirmed on a row whose accounts are already
        both known (unlike `confirm_pending_deposit_transaction`, which also
        fills in a previously-unknown destination). Returns True iff a row
        changed."""
        result = db.session.execute(
            update(Transaction)
            .where(Transaction.tx_id == tx_id, Transaction.status == STATUS_PENDING)
            .values(
                status=STATUS_CONFIRMED,
                confirmed_at=confirmed_at,
                processed_at=confirmed_at,
            )
        )
        return result.rowcount == 1

    def confirm_pending_transactions(
        self, tx_ids: list[uuid.UUID], confirmed_at: datetime
    ) -> bool:
        """Guarded pending -> confirmed on several rows in one UPDATE. Returns
        True iff every one of them changed. On False, any that *were* still
        pending have been confirmed in this session, so the caller must roll
        back rather than commit."""
        result = db.session.execute(
            update(Transaction)
            .where(
                Transaction.tx_id.in_(tx_ids),
                Transaction.status == STATUS_PENDING,
            )
            .values(
                status=STATUS_CONFIRMED,
                confirmed_at=confirmed_at,
                processed_at=confirmed_at,
            )
        )
        return result.rowcount == len(tx_ids)

    def fail_pending_transaction(self, tx_id: uuid.UUID) -> bool:
        """Guarded pending -> failed. Returns True iff a row changed."""
        result = db.session.execute(
            update(Transaction)
            .where(Transaction.tx_id == tx_id, Transaction.status == STATUS_PENDING)
            .values(status=STATUS_FAILED)
        )
        return result.rowcount == 1
