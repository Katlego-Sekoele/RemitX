import uuid

from sqlalchemy import select, update

from remitx_api.extensions import db
from remitx_api.models.orm.deposit import Deposit
from remitx_api.models.orm.transaction import STATUS_PENDING, Transaction
from remitx_api.repositories.repository import Repository


class DepositRepository(Repository[Deposit, uuid.UUID]):
    """Data access for `deposits`.

    Inherits get_by_id / list / save / delete from the shared Repository
    base and adds the query methods specific to this table.
    """

    def __init__(self) -> None:
        super().__init__(Deposit)

    def add(self, deposit: Deposit) -> Deposit:
        """Insert a new deposit row. Flushes only — caller commits."""
        db.session.add(deposit)
        db.session.flush()
        return deposit

    def list_user_deposits(self, user_id: uuid.UUID) -> list[Deposit]:
        """A user's deposits, newest first (ordered by the linked transaction)."""
        return db.session.scalars(
            select(Deposit)
            .join(Transaction, Deposit.tx_id == Transaction.tx_id)
            .where(Deposit.user_id == user_id)
            .order_by(Transaction.created_at.desc())
        ).all()

    def list_pending_deposits(self) -> list[Deposit]:
        """Deposits still unmatched to a user, for the admin portal to list."""
        return db.session.scalars(
            select(Deposit)
            .join(Transaction, Deposit.tx_id == Transaction.tx_id)
            .where(Transaction.status == STATUS_PENDING)
            .order_by(Transaction.created_at)
        ).all()

    def link_deposit_to_user(
        self, deposit_id: uuid.UUID, user_id: uuid.UUID, confirmed_by: str
    ) -> bool:
        """Attribute an unmatched deposit to a user. Returns True iff a row changed.

        Called only after the linked transaction's own pending->confirmed
        guard has already succeeded — this just records who it belongs to.
        """
        result = db.session.execute(
            update(Deposit)
            .where(Deposit.deposit_id == deposit_id, Deposit.user_id.is_(None))
            .values(user_id=user_id, confirmed_by=confirmed_by)
        )
        return result.rowcount == 1
