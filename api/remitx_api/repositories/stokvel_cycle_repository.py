import uuid
from datetime import datetime

from sqlalchemy import Select, exists, select, update

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.repositories.repository import Repository


def locked_members_query(cycle_id: uuid.UUID) -> Select:
    """A started cycle's members, in payout order. The cycle's members are its
    locked rows: a member who left before it started keeps an unlocked row
    with no position, and is not in it (R2-10). Shared with the worker, which
    runs it on its own session."""
    return (
        select(StokvelCycleMember)
        .where(
            StokvelCycleMember.cycle_id == cycle_id,
            StokvelCycleMember.locked.is_(True),
        )
        .order_by(StokvelCycleMember.payout_position)
    )


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

    def get_latest_cycle(self, stokvel_id: uuid.UUID) -> StokvelCycle | None:
        """The stokvel's highest-numbered cycle, closed ones included."""
        return db.session.scalars(
            select(StokvelCycle)
            .where(StokvelCycle.stokvel_id == stokvel_id)
            .order_by(StokvelCycle.cycle_number.desc())
            .limit(1)
        ).one_or_none()

    def has_any_cycle(self, stokvel_id: uuid.UUID) -> bool:
        """Whether the stokvel has ever had a cycle, closed ones included."""
        return db.session.scalar(
            select(exists().where(StokvelCycle.stokvel_id == stokvel_id))
        )

    def add_forming_cycle(
        self, stokvel_id: uuid.UUID, cycle_number: int = 1
    ) -> StokvelCycle:
        """Stage a new `forming` cycle: no rounds, start or schedule yet."""
        return self.add(
            StokvelCycle(
                stokvel_id=stokvel_id,
                cycle_number=cycle_number,
                status=StokvelCycleStatus.FORMING.value,
            )
        )

    def get_cycle_member(
        self, cycle_id: uuid.UUID, member_id: uuid.UUID
    ) -> StokvelCycleMember | None:
        """The member's row in the cycle, if they have one."""
        return db.session.get(StokvelCycleMember, (cycle_id, member_id))

    def add_cycle_member(
        self, cycle_id: uuid.UUID, member_id: uuid.UUID
    ) -> StokvelCycleMember:
        """Stage the member's row in the cycle, with no payout position or
        beneficiary yet."""
        member = StokvelCycleMember(cycle_id=cycle_id, member_id=member_id)
        db.session.add(member)
        db.session.flush()
        return member

    def pays_beneficiary(self, beneficiary_id: uuid.UUID) -> bool:
        """Whether any cycle row, of any status, pays this beneficiary. On
        Postgres the caller sees the rows of every stokvel they are or were a
        member of, so their own choices are always visible."""
        return db.session.scalar(
            select(
                exists().where(
                    StokvelCycleMember.payout_beneficiary_id == beneficiary_id
                )
            )
        )

    def clear_payout_positions(self, cycle_id: uuid.UUID) -> None:
        """Clear every payout position in the cycle, former members' rows
        included, so a new order can be written row by row without meeting
        `uq_stokvel_cycle_members_cycle_id_position` halfway."""
        db.session.execute(
            update(StokvelCycleMember)
            .where(StokvelCycleMember.cycle_id == cycle_id)
            .values(payout_position=None)
        )
        db.session.flush()

    def add_round(
        self,
        cycle_id: uuid.UUID,
        round_: int,
        *,
        start_time: datetime,
        deadline: datetime,
        payout_time: datetime,
    ) -> StokvelRound:
        """Stage one round's times. A cycle's rounds are written once, when it
        starts. Flushes only."""
        row = StokvelRound(
            cycle_id=cycle_id,
            round=round_,
            start_time=start_time,
            deadline=deadline,
            payout_time=payout_time,
        )
        db.session.add(row)
        db.session.flush()
        return row

    def get_cycle_rounds(self, cycle_id: uuid.UUID) -> list[StokvelRound]:
        """Get the information about the rounds in a cycle, for a given cycle_id."""
        return list(
            db.session.scalars(
                select(StokvelRound)
                .where(StokvelRound.cycle_id == cycle_id)
                .order_by(StokvelRound.round)
            ).all()
        )

    def get_cycle_members(self, cycle_id: uuid.UUID) -> list[StokvelCycleMember]:
        """Get members of a cycle, ordered by their payout position,
        for a given cycle_id."""
        return list(
            db.session.scalars(
                select(StokvelCycleMember)
                .where(StokvelCycleMember.cycle_id == cycle_id)
                .order_by(
                    StokvelCycleMember.payout_position.is_(None),
                    StokvelCycleMember.payout_position,
                )
            ).all()
        )

    def get_locked_members(self, cycle_id: uuid.UUID) -> list[StokvelCycleMember]:
        """A started cycle's members, in payout order (`locked_members_query`).
        `get_cycle_members` also returns former members' unlocked rows."""
        return list(db.session.scalars(locked_members_query(cycle_id)).all())
