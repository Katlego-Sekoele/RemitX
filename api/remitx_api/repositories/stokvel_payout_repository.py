import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.repositories.repository import Repository


class StokvelPayoutRepository(Repository[StokvelPayout, uuid.UUID]):
    """Repository for stokvel payouts, one per round. Queries here run under
    row-level security on Postgres; SQLite (tests) does not filter, so callers
    scope by user."""

    def __init__(self) -> None:
        super().__init__(StokvelPayout)

    def get_round_payout(
        self, cycle_id: uuid.UUID, round_: int
    ) -> StokvelPayout | None:
        """Get the payout of one round of a cycle. Returns None if the round
        has no payout yet."""
        return db.session.scalars(
            select(StokvelPayout).where(
                StokvelPayout.cycle_id == cycle_id,
                StokvelPayout.round == round_,
            )
        ).one_or_none()

    def get_cycle_payouts(self, cycle_id: uuid.UUID) -> list[StokvelPayout]:
        """Get the payouts of a cycle, in round order."""
        return list(
            db.session.scalars(
                select(StokvelPayout)
                .where(StokvelPayout.cycle_id == cycle_id)
                .order_by(StokvelPayout.round)
            ).all()
        )
