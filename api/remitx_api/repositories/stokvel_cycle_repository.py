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

    def get_open_cycle(self, stokvel_id: uuid.UUID) -> StokvelCycle | None:
        """Get the cycle for a given stokvel_id that is not closed. (forming or active).
        Returns None if no such cycle exists."""
        return db.session.scalars(
            select(StokvelCycle).where(
                StokvelCycle.stokvel_id == stokvel_id,
                StokvelCycle.status != StokvelCycleStatus.CLOSED.value,
            )
        ).one_or_none()

    def get_cycle_rounds(self, cycle_id: uuid.UUID) -> list[StokvelRound]:
        """Get the information about the rounds in a cycle, for a given cycle_id."""
        return db.session.scalars(
            select(StokvelRound)
            .where(StokvelRound.cycle_id == cycle_id)
            .order_by(StokvelRound.round)
        ).all()

    def get_cycle_members(self, cycle_id: uuid.UUID) -> list[StokvelCycleMember]:
        """Get members of a cycle, ordered by their payout position,
        for a given cycle_id."""
        return db.session.scalars(
            select(StokvelCycleMember)
            .where(StokvelCycleMember.cycle_id == cycle_id)
            .order_by(
                StokvelCycleMember.payout_position.is_(None),
                StokvelCycleMember.payout_position,
            )
        ).all()
