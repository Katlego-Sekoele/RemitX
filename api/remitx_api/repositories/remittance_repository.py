import uuid

from sqlalchemy import or_, select

from remitx_api.extensions import db
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.repositories.repository import Repository


class RemittanceRepository(Repository[Remittance, uuid.UUID]):
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
