import uuid
from datetime import datetime

from sqlalchemy import select, update

from remitx_api.extensions import db
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
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
