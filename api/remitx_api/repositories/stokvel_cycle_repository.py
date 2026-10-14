import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.repositories.repository import Repository


class StokvelCycleRepository(Repository[StokvelCycle, uuid.UUID]):
    """Repository for stokvel cycles, their rounds and their members. Queries
    here run under row-level security on Postgres; SQLite (tests) does not
    filter, so callers scope by user."""

    def __init__(self) -> None:
        super().__init__(StokvelCycle)

    def open_cycle(self, stokvel_id: uuid.UUID) -> StokvelCycle | None:
        """The stokvel's cycle that is not closed yet, if any (at most one)."""
        return db.session.scalars(
            select(StokvelCycle).where(
                StokvelCycle.stokvel_id == stokvel_id,
                StokvelCycle.status != StokvelCycleStatus.CLOSED.value,
            )
        ).one_or_none()

    def rounds(self, cycle_id: uuid.UUID) -> list[StokvelRound]:
        """The cycle's rounds, first to last."""
        return db.session.scalars(
            select(StokvelRound)
            .where(StokvelRound.cycle_id == cycle_id)
            .order_by(StokvelRound.round)
        ).all()

    def members(self, cycle_id: uuid.UUID) -> list[StokvelCycleMember]:
        """The cycle's members in payout order; any without a position yet
        come last."""
        return db.session.scalars(
            select(StokvelCycleMember)
            .where(StokvelCycleMember.cycle_id == cycle_id)
            .order_by(
                StokvelCycleMember.payout_position.is_(None),
                StokvelCycleMember.payout_position,
            )
        ).all()
