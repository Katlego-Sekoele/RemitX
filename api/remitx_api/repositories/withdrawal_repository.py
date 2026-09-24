import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.transaction import Transaction
from remitx_api.models.orm.withdrawal import Withdrawal
from remitx_api.repositories.repository import Repository


class WithdrawalRepository(Repository[Withdrawal, uuid.UUID]):
    """Repository for Withdrawal ORM objects."""

    def __init__(self) -> None:
        super().__init__(Withdrawal)

    def add(self, withdrawal: Withdrawal) -> Withdrawal:
        """Insert a withdrawal. Flushes only — caller commits."""
        db.session.add(withdrawal)
        db.session.flush()
        return withdrawal

    def list_user_withdrawals(
        self, user_id: uuid.UUID
    ) -> list[tuple[Withdrawal, Transaction]]:
        """A user's withdrawals, newest first, each paired with its withdrawal
        transaction — status lives there, not on Withdrawal (see
        models/orm/withdrawal.py), so the caller needn't fetch it per row."""
        return db.session.execute(
            select(Withdrawal, Transaction)
            .join(Transaction, Withdrawal.tx_id == Transaction.tx_id)
            .where(Withdrawal.user_id == user_id)
            .order_by(Transaction.created_at.desc())
        ).all()
