import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.remittance import Remittance
from remitx_api.repositories.repository import Repository


class RemittanceRepository(Repository[Remittance, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(Remittance)

    def get_by_quote_id(self, quote_id: uuid.UUID) -> Remittance | None:
        """The remittance a quote was confirmed into, if any — `quote_id` is
        UNIQUE, so at most one exists."""
        return db.session.scalars(
            select(Remittance).where(Remittance.quote_id == quote_id)
        ).first()
