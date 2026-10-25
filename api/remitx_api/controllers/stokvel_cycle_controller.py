"""Starting a stokvel's cycle (R2-10, #232).

The Organiser starts the forming cycle once at least two members are ready:
each has a place in the payout order and a payout beneficiary (R2-09). In one
transaction, holding the `stokvels` row lock as the setup routes and accepting
an invitation do, so none of them can interleave with the start:

1. the round schedule is written, one round per member, in payout order;
2. invitations still pending lapse: their invitee is not in this cycle;
3. the current members' cycle rows are locked, with their order and
   beneficiaries. A former member's row stays, unlocked: the cycle's members
   are its locked rows. From cycle 2, only members who chose to continue (or
   joined since) are in it; anyone else from the closed cycle leaves now
   (R2-15, `going_into`);
4. the cycle becomes `active`, with its number of rounds.

The token contribution is already fixed: it is the stokvel's
`contribution_amount` for its whole life (D13).

After the commit the worker registers the cycle on the contract
(`stokvel.start_cycle`: `createStokvel` for a new stokvel, then
`startCycle`). Contributions wait for that (`registered_at`), because the
contract has no open cycle until `startCycle` is mined.

When a cycle closes, `open_next_cycle` opens the next one as `forming`
(R2-15, #237), so its members can choose to continue or leave and the
Organiser can set it up and start it the same way.

The checks mirror the contract's `startCycle` rules (doc section 1), so a
cycle that starts here is one the contract accepts: at least `MIN_MEMBERS`
and at most `maxMembers` members, one round each, start <= deadline <= payout
within a round, and start and payout times that never go backwards.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from remitx_api.clock import utcnow
from remitx_api.config import Config
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    CycleAlreadyStartedError,
    CycleNotFormingError,
    CycleNotReadyError,
    InvalidCycleScheduleError,
    NotStokvelOrganiserError,
    StokvelDeactivatedError,
    StokvelNotFoundError,
    TooFewMembersError,
    TooManyMembersError,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.repositories.stokvel_cycle_repository import (
    StokvelCycleRepository,
    locked_members_query,
)
from remitx_api.repositories.stokvel_invitation_repository import (
    StokvelInvitationRepository,
)
from remitx_api.repositories.stokvel_member_repository import StokvelMemberRepository
from remitx_api.repositories.stokvel_repository import StokvelRepository
from remitx_api.services import queue_service

logger = logging.getLogger(__name__)

# The contract's `MIN_MEMBERS` (StokvelVault.sol): `startCycle` reverts
# `TooFewMembers` below it.
MIN_CYCLE_MEMBERS = 2


@dataclass(frozen=True)
class RoundTimes:
    """One round's schedule, as the Organiser sets it. Aware datetimes."""

    start_time: datetime
    deadline: datetime
    payout_time: datetime


@dataclass(frozen=True)
class CycleRoundView:
    round: int
    start_time: datetime
    deadline: datetime
    payout_time: datetime


@dataclass(frozen=True)
class CyclePlaceView:
    member_id: uuid.UUID
    payout_position: int
    beneficiary_id: uuid.UUID
    payout_currency: str


@dataclass(frozen=True)
class StartedCycleView:
    stokvel_id: uuid.UUID
    cycle_id: uuid.UUID
    cycle_number: int
    status: str
    total_rounds: int
    current_round: int
    started_at: datetime
    # None until the worker has registered the cycle on-chain
    registered_at: datetime | None
    rounds: list[CycleRoundView]
    order: list[CyclePlaceView]
    lapsed_invitations: int


def going_into(
    cycle: StokvelCycle, current: list[StokvelMember], cycles: StokvelCycleRepository
) -> list[StokvelMember]:
    """The current members who go into the forming `cycle` (R2-15). Cycle 1:
    all of them. A later cycle: those with a row in it, so the Organiser,
    each member of the closed cycle who chose to continue, and everyone who
    joined since. A member of the closed cycle who has not chosen is not in
    it, and is treated as leaving when it starts."""
    if cycle.cycle_number == 1:
        return current
    with_rows = {row.member_id for row in cycles.get_cycle_members(cycle.id)}
    return [member for member in current if member.id in with_rows]


def open_next_cycle(session, closed: StokvelCycle) -> StokvelCycle | None:
    """Open the cycle after `closed` as `forming` and make it the stokvel's
    current cycle (R2-15, #237). Flushes only; the caller commits.

    Rows in the new cycle, with no payout position yet:

    - the Organiser, who cannot leave, carried over with their beneficiary
      (re-checked at payout time, as every choice is); their row in `closed`
      is marked `continued`
    - each current member who was not in `closed` (they joined while it
      ran), empty: they have not been in a cycle to continue from

    Everyone else in `closed` gets a row only by choosing to continue.

    Shared by the worker, when it records `CycleClosed`, and the Organiser's
    first setup call for a cycle that closed before this existed, so it runs
    on the caller's `session`. Holds the `stokvels` row lock, as accepting an
    invitation does, so a member who joins meanwhile is not missed. None,
    and nothing changes, if the stokvel is deactivated or a cycle is already
    open.
    """
    stokvel = session.scalars(
        select(Stokvel).where(Stokvel.id == closed.stokvel_id).with_for_update()
    ).one_or_none()
    if stokvel is None or stokvel.deactivated_at is not None:
        return None
    already_open = session.scalar(
        select(StokvelCycle.id).where(
            StokvelCycle.stokvel_id == stokvel.id,
            StokvelCycle.status != StokvelCycleStatus.CLOSED.value,
        )
    )
    if already_open is not None:
        return None

    cycle = StokvelCycle(
        stokvel_id=stokvel.id,
        cycle_number=closed.cycle_number + 1,
        status=StokvelCycleStatus.FORMING.value,
    )
    session.add(cycle)
    session.flush()

    was_in = {
        row.member_id: row for row in session.scalars(locked_members_query(closed.id))
    }
    current = session.scalars(
        select(StokvelMember).where(
            StokvelMember.stokvel_id == stokvel.id,
            StokvelMember.left_at.is_(None),
        )
    )
    for member in current:
        before = was_in.get(member.id)
        if member.user_id == stokvel.organiser_user_id:
            session.add(
                StokvelCycleMember(
                    cycle_id=cycle.id,
                    member_id=member.id,
                    payout_beneficiary_id=(
                        None if before is None else before.payout_beneficiary_id
                    ),
                    payout_currency=None if before is None else before.payout_currency,
                )
            )
            if before is not None:
                before.continued = True
        elif before is None:
            session.add(StokvelCycleMember(cycle_id=cycle.id, member_id=member.id))
    stokvel.current_cycle_id = cycle.id
    session.flush()
    return cycle


class StokvelCycleController:
    def __init__(self) -> None:
        self._cycles = StokvelCycleRepository()
        self._invitations = StokvelInvitationRepository()
        self._members = StokvelMemberRepository()
        self._stokvels = StokvelRepository()

    def start_cycle(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID, schedule: list[RoundTimes]
    ) -> StartedCycleView:
        """Start the stokvel's forming cycle with `schedule` (`schedule[i]` is
        round i, which pays the member at payout position i), then queue its
        registration on-chain. Enqueued only after the commit, so the worker
        never sees a start that might still roll back."""
        view = self._start(user_id, stokvel_id, schedule)
        # The cycle is committed `active` now, so the start has happened: a
        # 500 would only make the Organiser retry into `cycle_in_progress`.
        # A lost enqueue is picked up by the worker's sweep
        # (`stokvel.register_started_cycles`), so it is logged, not raised.
        try:
            queue_service.enqueue_start_cycle(str(view.cycle_id))
        except Exception:
            logger.exception(
                "start_cycle: failed to enqueue start_cycle for cycle %s "
                "(stokvel %s); committed active, the sweep will queue it",
                view.cycle_id,
                view.stokvel_id,
            )
        return view

    @db_transaction
    def _start(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID, schedule: list[RoundTimes]
    ) -> StartedCycleView:
        # Held until the commit: no setup call or accept can change the
        # members, order or beneficiaries while they are checked and locked.
        stokvel = self._stokvels.lock(stokvel_id)
        if stokvel is None:
            raise StokvelNotFoundError()
        # Not a current member: the same 404 as an unknown id.
        if self._members.get_active_member(stokvel.id, user_id) is None:
            raise StokvelNotFoundError()
        if stokvel.organiser_user_id != user_id:
            raise NotStokvelOrganiserError("start a cycle")
        if stokvel.deactivated_at is not None:
            raise StokvelDeactivatedError()
        cycle = self._cycles.get_open_cycle(stokvel.id)
        if cycle is None:
            raise CycleNotFormingError()
        if cycle.status != StokvelCycleStatus.FORMING.value:
            raise CycleAlreadyStartedError()

        current = self._members.list_active(stokvel.id)
        members = going_into(cycle, current, self._cycles)
        max_members = Config().MAX_STOKVEL_MEMBERS
        if len(members) < MIN_CYCLE_MEMBERS:
            raise TooFewMembersError(MIN_CYCLE_MEMBERS)
        if len(members) > max_members:
            raise TooManyMembersError(max_members)
        rows = self._ready_rows(cycle.id, [member.id for member in members])
        times = _checked_schedule(schedule, len(rows))

        for round_, round_times in enumerate(times):
            self._cycles.add_round(
                cycle.id,
                round_,
                start_time=round_times.start_time,
                deadline=round_times.deadline,
                payout_time=round_times.payout_time,
            )
        now = utcnow()
        lapsed = self._invitations.lapse_pending(stokvel.id, by_user_id=user_id, at=now)
        going = {member.id for member in members}
        self._end_undecided(
            cycle, [member for member in current if member.id not in going], at=now
        )
        for row in rows:
            row.locked = True
        cycle.status = StokvelCycleStatus.ACTIVE.value
        cycle.started_at = now
        cycle.total_rounds = len(rows)
        cycle.current_round = 0
        stokvel.current_cycle_id = cycle.id

        return StartedCycleView(
            stokvel_id=stokvel.id,
            cycle_id=cycle.id,
            cycle_number=cycle.cycle_number,
            status=cycle.status,
            total_rounds=cycle.total_rounds,
            current_round=cycle.current_round,
            started_at=now,
            registered_at=cycle.registered_at,
            rounds=[
                CycleRoundView(
                    round=round_,
                    start_time=round_times.start_time,
                    deadline=round_times.deadline,
                    payout_time=round_times.payout_time,
                )
                for round_, round_times in enumerate(times)
            ],
            order=[
                CyclePlaceView(
                    member_id=row.member_id,
                    payout_position=row.payout_position,
                    beneficiary_id=row.payout_beneficiary_id,
                    payout_currency=row.payout_currency,
                )
                for row in rows
            ],
            lapsed_invitations=lapsed,
        )

    def _end_undecided(
        self, cycle: StokvelCycle, undecided: list[StokvelMember], *, at: datetime
    ) -> None:
        """Members of the closed cycle who never chose to continue or leave
        are treated as leaving now (R2-15): their membership ends and their
        row in the closed cycle records `continued` as false. Row-level
        security lets the Organiser make only this change to another
        member's membership (`V20261022_1000`)."""
        if not undecided:
            return
        closed = self._cycles.get_cycle_by_number(
            cycle.stokvel_id, cycle.cycle_number - 1
        )
        for member in undecided:
            member.left_at = at
            before = self._cycles.get_cycle_member(closed.id, member.id)
            if before is not None and before.locked:
                before.continued = False

    def _ready_rows(
        self, cycle_id: uuid.UUID, member_ids: list[uuid.UUID]
    ) -> list[StokvelCycleMember]:
        """The current members' cycle rows, in payout order, once every one
        has a position and a beneficiary and the positions are exactly
        `0..n-1`.

        Each row having a position is not enough (doc section 8): a member
        who left after the order was set keeps theirs until the next order,
        leaving a gap no current member fills, and a member who joined since
        has none.
        """
        by_member = {
            row.member_id: row for row in self._cycles.get_cycle_members(cycle_id)
        }
        rows = []
        for member_id in member_ids:
            row = by_member.get(member_id)
            if row is None or row.payout_position is None:
                raise CycleNotReadyError.order_missing()
            rows.append(row)
        if {row.payout_position for row in rows} != set(range(len(rows))):
            raise CycleNotReadyError.order_out_of_date()
        if any(row.payout_beneficiary_id is None for row in rows):
            raise CycleNotReadyError.beneficiary_missing()
        return sorted(rows, key=lambda row: row.payout_position)


def _checked_schedule(schedule: list[RoundTimes], members: int) -> list[RoundTimes]:
    """`schedule` in UTC, to the whole second, once it is one round per member
    and its times follow the contract's rules: start <= deadline <= payout
    within a round, and start and payout times that never go backwards from
    one round to the next (equal is allowed).

    Whole seconds because the contract holds `uint64` seconds: the rounds
    stored here are then exactly the ones `startCycle` is sent."""
    if len(schedule) != members:
        raise InvalidCycleScheduleError.wrong_length(members)
    times = [
        RoundTimes(
            start_time=_utc_second(item.start_time),
            deadline=_utc_second(item.deadline),
            payout_time=_utc_second(item.payout_time),
        )
        for item in schedule
    ]
    for round_, item in enumerate(times):
        if not item.start_time <= item.deadline <= item.payout_time:
            raise InvalidCycleScheduleError.out_of_order(round_)
        if round_ and (
            item.start_time < times[round_ - 1].start_time
            or item.payout_time < times[round_ - 1].payout_time
        ):
            raise InvalidCycleScheduleError.goes_backwards(round_)
    return times


def _utc_second(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(microsecond=0)
