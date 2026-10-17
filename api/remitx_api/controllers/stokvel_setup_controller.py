"""Setting up a stokvel's next cycle before it starts (R2-09): the Organiser
enters the payout order the members agreed off the platform (D3).

Everything here happens while the cycle is `forming` and is locked once it
starts (R2-10). Each use case holds the stokvel row lock, as accepting an
invitation does, so a join or a second setup call cannot interleave.

A stokvel created before cycles opened at creation has none. The Organiser's
first setup call opens cycle 1 for it; row-level security lets only the
Organiser insert a cycle. Members from before then get their cycle row the
same way. Cycle 2 onwards is opened by #237, not here.
"""

import uuid
from dataclasses import dataclass

from remitx_api.controllers.stokvel_controller import open_forming_cycle
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    CycleNotFormingError,
    InvalidPayoutOrderError,
    NotStokvelOrganiserError,
    PayoutSetupLockedError,
    StokvelDeactivatedError,
    StokvelNotFoundError,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.user import short_display_name
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


class StokvelSetupController:
    def __init__(self) -> None:
        self._cycles = StokvelCycleRepository()
        self._members = StokvelMemberRepository()
        self._stokvels = StokvelRepository()
        self._users = UserRepository()

    @db_transaction
    def set_payout_order(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID, member_ids: list[uuid.UUID]
    ) -> PayoutOrderView:
        """Replace the forming cycle's payout order: `member_ids[i]` is paid
        in round i. It must name every current member exactly once.

        Re-ordering updates rows in place (there is no delete). A former
        member keeps their cycle row but loses its position, so it neither
        collides with the new order nor counts as placed when the cycle
        starts.
        """
        stokvel = self._lock_own_stokvel(user_id, stokvel_id)
        if stokvel.organiser_user_id != user_id:
            raise NotStokvelOrganiserError("set the payout order")
        if stokvel.deactivated_at is not None:
            raise StokvelDeactivatedError()
        cycle = self._forming_cycle(stokvel, is_organiser=True)

        current = self._members.list_active(stokvel.id)
        self._check_order(stokvel.id, member_ids, {m.id for m in current})
        rows = {
            member.id: self._cycles.get_cycle_member(cycle.id, member.id)
            or self._cycles.add_cycle_member(cycle.id, member.id)
            for member in current
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

    def _lock_own_stokvel(self, user_id: uuid.UUID, stokvel_id: uuid.UUID) -> Stokvel:
        """The stokvel, locked until the transaction ends, if `user_id` is a
        current member. Anyone else gets the same 404 as an unknown id."""
        stokvel = self._stokvels.lock(stokvel_id)
        if stokvel is None:
            raise StokvelNotFoundError()
        if self._members.get_active_member(stokvel.id, user_id) is None:
            raise StokvelNotFoundError()
        return stokvel

    def _forming_cycle(self, stokvel: Stokvel, *, is_organiser: bool) -> StokvelCycle:
        """The stokvel's open cycle, if it is still `forming`. A stokvel that
        has never had a cycle gets cycle 1, but only from its Organiser."""
        cycle = self._cycles.get_open_cycle(stokvel.id)
        if cycle is None:
            if not is_organiser or self._cycles.has_any_cycle(stokvel.id):
                raise CycleNotFormingError()
            return open_forming_cycle(stokvel)
        if cycle.status != StokvelCycleStatus.FORMING.value:
            raise PayoutSetupLockedError()
        return cycle

    def _check_order(
        self,
        stokvel_id: uuid.UUID,
        member_ids: list[uuid.UUID],
        current_ids: set[uuid.UUID],
    ) -> None:
        if len(set(member_ids)) != len(member_ids):
            raise InvalidPayoutOrderError.duplicate()
        for member_id in member_ids:
            if member_id in current_ids:
                continue
            member: StokvelMember | None = self._members.get_by_id(member_id)
            if member is not None and member.stokvel_id == stokvel_id:
                raise InvalidPayoutOrderError.former_member()
            raise InvalidPayoutOrderError.unknown_member()
        if set(member_ids) != current_ids:
            raise InvalidPayoutOrderError.missing_member()


def _name(user) -> str | None:
    return None if user is None else short_display_name(user.first_name, user.last_name)
