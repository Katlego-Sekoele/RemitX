import uuid
from datetime import datetime

from sqlalchemy import select, update

from remitx_api.extensions import db
from remitx_api.models.orm.quote import STATUS_ACTIVE, STATUS_USED, Quote
from remitx_api.repositories.repository import Repository


class QuoteRepository(Repository[Quote, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(Quote)

    def get_for_sender(
        self, quote_id: uuid.UUID, sender_user_id: uuid.UUID
    ) -> Quote | None:
        """A quote by id, scoped to the sender who owns it.

        Collapses "doesn't exist" and "exists but isn't yours" into one
        `None`.
        """
        return db.session.scalars(
            select(Quote).where(
                Quote.quote_id == quote_id, Quote.sender_user_id == sender_user_id
            )
        ).first()

    def mark_used(self, quote_id: uuid.UUID, now: datetime) -> bool:
        """Guarded ACTIVE -> USED transition, confirming a remittance.

        Guarded on both `status='ACTIVE'` and `expires_at > now` in the same
        WHERE — nothing ever sweeps a quote to EXPIRED, so an expired-but-
        still-ACTIVE row is the normal steady state, and checking expiry
        outside the guard would leave a race window right at the boundary.
        """
        result = db.session.execute(
            update(Quote)
            .where(
                Quote.quote_id == quote_id,
                Quote.status == STATUS_ACTIVE,
                Quote.expires_at > now,
            )
            .values(status=STATUS_USED)
            # We don't have the Quote object in memory, so don't try to
            # update it.
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1  #  Returns True iff a row changed
