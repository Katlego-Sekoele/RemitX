import uuid
from datetime import datetime

from sqlalchemy import or_, select, update

from remitx_api.extensions import db
from remitx_api.models.orm.account import TYPE_USER, Account
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    TYPE_TOKEN_BURN,
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

    def list_account_transactions(
        self,
        account_id: uuid.UUID,
        limit: int | None = None,
        before: datetime | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[Transaction]:
        """Legs touching this account, either side, newest first — an
        account's transaction history. `credit`=source, `debit`=destination
        (models/orm/transaction.py), so an account can appear on either side
        depending on the leg.

        `limit` caps the page; `before` is a cursor that keeps only legs
        created strictly earlier, so the next page starts from the last
        row's `created_at`.

        A customer read passes `user_id`. The account must be that person's
        own `USER` account, or the page is empty. Settlement code omits it
        and reads platform accounts; on Postgres a customer session is also
        limited by the `transactions` row-level security policy.
        """
        query = select(Transaction).where(
            or_(
                Transaction.credit_account_id == account_id,
                Transaction.debit_account_id == account_id,
            )
        )
        if user_id is not None:
            query = query.where(
                select(Account.account_id)
                .where(
                    Account.account_id == account_id,
                    Account.type == TYPE_USER,
                    Account.user_id == user_id,
                )
                .exists()
            )
        query = query.order_by(Transaction.created_at.desc(), Transaction.tx_id.desc())
        if before is not None:
            query = query.where(Transaction.created_at < before)
        if limit is not None:
            query = query.limit(limit)
        return db.session.scalars(query).all()

    def get_burn_hashes(
        self, quote_ids: set[uuid.UUID], user_id: uuid.UUID
    ) -> dict[uuid.UUID, str]:
        """Confirmed burn hashes for quotes this customer sent or received.

        The hash lives only on the `token_burn` leg, which moves money
        between platform accounts, so account ownership does not cover it.
        The quote's parties do. Postgres row-level security on
        `transactions` applies the same rule.
        """
        if not quote_ids:
            return {}
        rows = db.session.execute(
            select(Transaction.quote_id, Transaction.xrpl_tx_hash)
            .join(Quote, Quote.quote_id == Transaction.quote_id)
            .where(
                Transaction.quote_id.in_(quote_ids),
                Transaction.type == TYPE_TOKEN_BURN,
                Transaction.status == STATUS_CONFIRMED,
                Transaction.xrpl_tx_hash.is_not(None),
                or_(
                    Quote.sender_user_id == user_id,
                    Quote.beneficiary_user_id == user_id,
                ),
            )
        ).all()
        return {quote_id: tx_hash for quote_id, tx_hash in rows}

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

    def fail_pending_transaction(self, tx_id: uuid.UUID) -> bool:
        """Guarded pending -> failed. Returns True iff a row changed."""
        result = db.session.execute(
            update(Transaction)
            .where(Transaction.tx_id == tx_id, Transaction.status == STATUS_PENDING)
            .values(status=STATUS_FAILED)
        )
        return result.rowcount == 1
