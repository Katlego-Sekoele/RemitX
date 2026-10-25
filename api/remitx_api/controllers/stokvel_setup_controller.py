"""Setting up a stokvel's next cycle before it starts (R2-09): the Organiser
enters the payout order the members agreed off the platform (D3), and each
member chooses the beneficiary the stokvel pays their pool to (#293). After
a cycle closes, each member of it first chooses to continue into the next or
leave (R2-15).

Everything here happens while the cycle is `forming` and is locked once it
starts (R2-10). Each use case holds the stokvel row lock, as accepting an
invitation does, so a join or a second setup call cannot interleave.

A stokvel created before cycles opened at creation has none. The Organiser's
first setup call opens cycle 1 for it; row-level security lets only the
Organiser insert a cycle. Members from before then get their cycle row the
same way. Cycle 2 onwards is opened by the worker when the previous cycle
closes (`open_next_cycle`, R2-15); the Organiser's first setup call opens it
for a cycle that closed before that existed.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from remitx_api.clock import utcnow
from remitx_api.controllers.stokvel_controller import open_forming_cycle
from remitx_api.controllers.stokvel_cycle_controller import (
    going_into,
    open_next_cycle,
)
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.beneficiaries import (
    PayoutAccountMissingError,
    UnknownBeneficiaryError,
)
from remitx_api.errors.stokvels import (
    CycleNotFormingError,
    InvalidPayoutOrderError,
    NothingToContinueError,
    NotStokvelOrganiserError,
    OrganiserCannotLeaveError,
    PayoutSetupLockedError,
    StokvelDeactivatedError,
    StokvelNotFoundError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.user import short_display_name
from remitx_api.repositories.beneficiary_repository import BeneficiaryRepository
from remitx_api.repositories.stokvel_cycle_repository import StokvelCycleRepository
from remitx_api.repositories.stokvel_member_repository import StokvelMemberRepository
from remitx_api.repositories.stokvel_repository import StokvelRepository
from remitx_api.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class PayoutPlaceView:
    member_id: uuid.UUID
    # 0-based: the round that pays this member
    payout_position: int
    # "Thandi M."; None when the member has no first name on file
    name: str | None


@dataclass(frozen=True)
class PayoutOrderView:
    stokvel_id: uuid.UUID
    cycle_number: int
    order: list[PayoutPlaceView]


@dataclass(frozen=True)
class PayoutBeneficiaryView:
    stokvel_id: uuid.UUID
    cycle_number: int
    member_id: uuid.UUID
    beneficiary_id: uuid.UUID
    payout_currency: str


class ContinuationChoice(StrEnum):
    CONTINUE = "continue"
    LEAVE = "leave"


@dataclass(frozen=True)
class ContinuationView:
    stokvel_id: uuid.UUID
    # The cycle the choice is for: the one after the cycle that closed
    cycle_number: int
    member_id: uuid.UUID
    choice: ContinuationChoice
    # The payout choice carried into the cycle; None on leaving, or for a
    # member continuing who has never chosen one
    beneficiary_id: uuid.UUID | None
    payout_currency: str | None


class StokvelSetupController:
    def __init__(self) -> None:
        self._beneficiaries = BeneficiaryRepository()
        self._cycles = StokvelCycleRepository()
        self._members = StokvelMemberRepository()
        self._stokvels = StokvelRepository()
        self._users = UserRepository()

    @db_transaction
    def set_payout_order(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID, member_ids: list[uuid.UUID]
    ) -> PayoutOrderView:
        """Replace the forming cycle's payout order: `member_ids[i]` is paid
        in round i. It must name every member going into the cycle exactly
        once: every current member for cycle 1, and from cycle 2 those who
        chose to continue or joined since (`going_into`, R2-15).

        Re-ordering updates rows in place (there is no delete). A former
        member keeps their cycle row but loses its position, so it neither
        collides with the new order nor counts as placed when the cycle
        starts.
        """
        stokvel, _member = self._lock_own_stokvel(user_id, stokvel_id)
        if stokvel.organiser_user_id != user_id:
            raise NotStokvelOrganiserError("set the payout order")
        if stokvel.deactivated_at is not None:
            raise StokvelDeactivatedError()
        cycle = self._forming_cycle(stokvel, is_organiser=True)

        current = self._members.list_active(stokvel.id)
        members = going_into(cycle, current, self._cycles)
        self._check_order(
            stokvel.id,
            member_ids,
            {m.id for m in members},
            undecided={m.id for m in current} - {m.id for m in members},
            first_cycle=cycle.cycle_number == 1,
        )
        rows = {
            member.id: self._cycles.get_cycle_member(cycle.id, member.id)
            or self._cycles.add_cycle_member(cycle.id, member.id)
            for member in members
        }
        self._cycles.clear_payout_positions(cycle.id)
        for position, member_id in enumerate(member_ids):
            rows[member_id].payout_position = position

        by_id = {member.id: member for member in current}
        users = self._users.get_many({member.user_id for member in current})
        return PayoutOrderView(
            stokvel_id=stokvel.id,
            cycle_number=cycle.cycle_number,
            order=[
                PayoutPlaceView(
                    member_id=member_id,
                    payout_position=position,
                    name=_name(users.get(by_id[member_id].user_id)),
                )
                for position, member_id in enumerate(member_ids)
            ],
        )

    @db_transaction
    def set_beneficiary(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID, beneficiary_id: uuid.UUID
    ) -> PayoutBeneficiaryView:
        """Choose which of the caller's own beneficiaries the stokvel pays
        their pool to in the forming cycle. Replaces any earlier choice.

        The payout currency is the beneficiary's own, copied now: changing
        the beneficiary later does not move a choice already made. The
        recipient must still hold a fiat account in it, as when the
        beneficiary was added.
        """
        stokvel, member = self._lock_own_stokvel(user_id, stokvel_id)
        if stokvel.deactivated_at is not None:
            raise StokvelDeactivatedError()
        cycle = self._forming_cycle(
            stokvel, is_organiser=stokvel.organiser_user_id == user_id
        )

        chosen, currency = self._checked_beneficiary(user_id, beneficiary_id)
        cycle_member = self._cycles.get_cycle_member(
            cycle.id, member.id
        ) or self._cycles.add_cycle_member(cycle.id, member.id)
        cycle_member.payout_beneficiary_id = chosen
        cycle_member.payout_currency = currency
        return PayoutBeneficiaryView(
            stokvel_id=stokvel.id,
            cycle_number=cycle.cycle_number,
            member_id=member.id,
            beneficiary_id=chosen,
            payout_currency=currency,
        )

    @db_transaction
    def continue_or_leave(
        self,
        user_id: uuid.UUID,
        stokvel_id: uuid.UUID,
        choice: ContinuationChoice,
        beneficiary_id: uuid.UUID | None = None,
    ) -> ContinuationView:
        """After a cycle closes, continue into the next one or leave the
        stokvel. Allowed while the next cycle is `forming`; a member who has
        not chosen by the time it starts is treated as leaving.

        Continuing gives the caller a row in the next cycle, paying
        `beneficiary_id` (checked as `set_beneficiary` does) or, without one,
        the choice already on that row or carried over from the closed
        cycle. It can be repeated, to change the beneficiary. The Organiser
        is continued already, and may call it to do the same.

        Leaving ends the membership: `left_at` is set and cannot be undone,
        so coming back needs a new invitation. The Organiser cannot leave.

        Either way the choice is recorded on the caller's row in the closed
        cycle (`continued`), if they were in it.
        """
        stokvel, member = self._lock_own_stokvel(user_id, stokvel_id)
        if stokvel.deactivated_at is not None:
            raise StokvelDeactivatedError()
        is_organiser = stokvel.organiser_user_id == user_id
        cycle = self._forming_cycle(stokvel, is_organiser=is_organiser)
        if cycle.cycle_number < 2:
            raise NothingToContinueError()
        closed = self._cycles.get_cycle_by_number(stokvel.id, cycle.cycle_number - 1)
        before = self._cycles.get_cycle_member(closed.id, member.id)
        if before is not None and not before.locked:
            # A row that was never locked: they were not in that cycle.
            before = None
        row = self._cycles.get_cycle_member(cycle.id, member.id)

        if choice == ContinuationChoice.LEAVE:
            if is_organiser:
                raise OrganiserCannotLeaveError()
            if before is not None:
                before.continued = False
            if row is not None:
                row.payout_position = None
            member.left_at = utcnow()
            return ContinuationView(
                stokvel_id=stokvel.id,
                cycle_number=cycle.cycle_number,
                member_id=member.id,
                choice=choice,
                beneficiary_id=None,
                payout_currency=None,
            )

        if row is None:
            row = self._cycles.add_cycle_member(cycle.id, member.id)
        if beneficiary_id is not None:
            chosen, currency = self._checked_beneficiary(user_id, beneficiary_id)
            row.payout_beneficiary_id, row.payout_currency = chosen, currency
        elif row.payout_beneficiary_id is None and before is not None:
            row.payout_beneficiary_id = before.payout_beneficiary_id
            row.payout_currency = before.payout_currency
        if before is not None:
            before.continued = True
        return ContinuationView(
            stokvel_id=stokvel.id,
            cycle_number=cycle.cycle_number,
            member_id=member.id,
            choice=choice,
            beneficiary_id=row.payout_beneficiary_id,
            payout_currency=row.payout_currency,
        )

    def _checked_beneficiary(
        self, user_id: uuid.UUID, beneficiary_id: uuid.UUID
    ) -> tuple[uuid.UUID, str]:
        """One of the caller's own beneficiaries and its payout currency,
        once the recipient still holds a fiat account in it, as when the
        beneficiary was added."""
        row = self._beneficiaries.get_sender_beneficiary(user_id, beneficiary_id)
        if row is None:
            raise UnknownBeneficiaryError(beneficiary_id)
        currency = row.beneficiary.payout_currency
        if currency not in row.payout_currencies:
            raise PayoutAccountMissingError(currency, row.payout_currencies)
        return row.beneficiary.beneficiary_id, currency

    def _lock_own_stokvel(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID
    ) -> tuple[Stokvel, StokvelMember]:
        """The stokvel, locked until the transaction ends, and the caller's
        current membership of it. Anyone who is not a current member gets the
        same 404 as an unknown id."""
        stokvel = self._stokvels.lock(stokvel_id)
        if stokvel is None:
            raise StokvelNotFoundError()
        member = self._members.get_active_member(stokvel.id, user_id)
        if member is None:
            raise StokvelNotFoundError()
        return stokvel, member

    def _forming_cycle(self, stokvel: Stokvel, *, is_organiser: bool) -> StokvelCycle:
        """The stokvel's open cycle, if it is still `forming`. When there is
        none, the Organiser opens one: cycle 1 for a stokvel that has never
        had a cycle, or the next after a closed one the worker did not open
        a successor for."""
        cycle = self._cycles.get_open_cycle(stokvel.id)
        if cycle is None:
            if not is_organiser:
                raise CycleNotFormingError()
            latest = self._cycles.get_latest_cycle(stokvel.id)
            if latest is None:
                return open_forming_cycle(stokvel)
            following = open_next_cycle(db.session, latest)
            if following is None:
                raise CycleNotFormingError()
            return following
        if cycle.status != StokvelCycleStatus.FORMING.value:
            raise PayoutSetupLockedError()
        return cycle

    def _check_order(
        self,
        stokvel_id: uuid.UUID,
        member_ids: list[uuid.UUID],
        current_ids: set[uuid.UUID],
        *,
        undecided: set[uuid.UUID],
        first_cycle: bool,
    ) -> None:
        """`member_ids` is `current_ids` (the members going into the cycle)
        exactly once. `undecided` are current members of the closed cycle
        who have not chosen to continue, so are not in it."""
        if len(set(member_ids)) != len(member_ids):
            raise InvalidPayoutOrderError.duplicate()
        for member_id in member_ids:
            if member_id in current_ids:
                continue
            if member_id in undecided:
                raise InvalidPayoutOrderError.not_continuing()
            member: StokvelMember | None = self._members.get_by_id(member_id)
            if member is not None and member.stokvel_id == stokvel_id:
                raise InvalidPayoutOrderError.former_member()
            raise InvalidPayoutOrderError.unknown_member()
        if set(member_ids) != current_ids:
            if first_cycle:
                raise InvalidPayoutOrderError.missing_member()
            raise InvalidPayoutOrderError.missing_continuing_member()


def _name(user) -> str | None:
    return None if user is None else short_display_name(user.first_name, user.last_name)
