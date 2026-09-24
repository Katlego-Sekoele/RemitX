import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import aliased

from remitx_api.extensions import db
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import TYPE_TOKEN_BURN, Transaction
from remitx_api.models.orm.user import User
from remitx_api.repositories.repository import Repository


@dataclass(frozen=True)
class RemittanceRecord:
    """A remittance with everything a transfer's page reads: the quote that
    priced it, the settlement leg whose status is the transfer's, the burn
    leg that carries the XRPL hash, and both people."""

    remittance: Remittance
    quote: Quote
    settlement_leg: Transaction
    # Always inserted with the group; outer-joined so a group missing one
    # still lists rather than vanishing.
    burn_leg: Transaction | None
    sender: User
    recipient: User


class RemittanceRepository(Repository[Remittance, uuid.UUID]):
    """Reads go through the request's row-level security context.

    Customer and admin routers bind ``app.current_user_id`` before the
    handler runs (``remitx_api.db.rls``, via ``create_customer_router``).
    Postgres then applies ``remittances_by_current_user``: a customer sees
    a transfer they sent or received, an admin route sees every transfer,
    and a worker with no bound user sees every row. The ``user_id`` filters
    below repeat that customer rule so SQLite tests, which have no
    row-level security, still hide someone else's transfer.
    """

    def __init__(self) -> None:
        super().__init__(Remittance)

    def get_ids_by_quote_ids(
        self, quote_ids: set[uuid.UUID], user_id: uuid.UUID
    ) -> dict[uuid.UUID, uuid.UUID]:
        """`remittance_id` for quotes this customer sent or received.

        Keyed by `quote_id`. A public history read must not resolve a
        remittance from a quote id alone: Postgres row-level security on
        `remittances` applies the same party check, and this join does it
        where that policy does not run.
        """
        if not quote_ids:
            return {}
        rows = db.session.execute(
            select(Remittance.quote_id, Remittance.remittance_id)
            .join(Quote, Quote.quote_id == Remittance.quote_id)
            .where(
                Remittance.quote_id.in_(quote_ids),
                or_(
                    Quote.sender_user_id == user_id,
                    Quote.beneficiary_user_id == user_id,
                ),
            )
        ).all()
        return {quote_id: remittance_id for quote_id, remittance_id in rows}

    def get_by_quote_id(self, quote_id: uuid.UUID) -> Remittance | None:
        """The remittance a quote was confirmed into, if any — `quote_id` is
        UNIQUE, so at most one exists."""
        return db.session.scalars(
            select(Remittance).where(Remittance.quote_id == quote_id)
        ).first()

    def list_for_user(self, user_id: uuid.UUID, limit: int) -> list[RemittanceRecord]:
        """The user's transfers, sent and received, newest first."""
        statement = (
            self._records()
            .where(
                or_(
                    Quote.sender_user_id == user_id,
                    Quote.beneficiary_user_id == user_id,
                )
            )
            .order_by(Remittance.created_at.desc(), Remittance.remittance_id)
            .limit(limit)
        )
        return [RemittanceRecord(*row) for row in db.session.execute(statement)]

    def get_for_user(
        self, remittance_id: uuid.UUID, user_id: uuid.UUID
    ) -> RemittanceRecord | None:
        """One transfer, if the user sent or received it. Collapses "doesn't
        exist" and "not yours" into one `None`."""
        statement = self._records().where(
            Remittance.remittance_id == remittance_id,
            or_(
                Quote.sender_user_id == user_id,
                Quote.beneficiary_user_id == user_id,
            ),
        )
        row = db.session.execute(statement).first()
        return RemittanceRecord(*row) if row else None

    @staticmethod
    def _records():
        settlement = aliased(Transaction)
        burn = aliased(Transaction)
        sender = aliased(User)
        recipient = aliased(User)
        return (
            select(Remittance, Quote, settlement, burn, sender, recipient)
            .join(Quote, Quote.quote_id == Remittance.quote_id)
            .join(settlement, settlement.tx_id == Remittance.tx_id)
            .outerjoin(
                burn,
                and_(
                    burn.quote_id == Remittance.quote_id,
                    burn.type == TYPE_TOKEN_BURN,
                ),
            )
            .join(sender, sender.id == Quote.sender_user_id)
            .join(recipient, recipient.id == Quote.beneficiary_user_id)
        )
