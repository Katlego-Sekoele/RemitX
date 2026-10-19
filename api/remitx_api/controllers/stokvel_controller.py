"""Creating stokvels, listing the caller's (R2-07) and reading one (R2-14).

A new stokvel opens its first cycle as `forming` (R2-09), so the Organiser
can set the payout order and members can choose their beneficiaries before
the cycle starts (R2-10).

Every query names the caller: Postgres row-level security would scope them
anyway, but SQLite (tests) has none, and the two must return the same rows.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from remitx_api.config import Config
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.stokvels import (
    KycNotApprovedToCreateStokvelError,
    StokvelCurrencyAccountMissingError,
    StokvelNotFoundError,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import STATUS_FAILED
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.models.orm.user import User, short_display_name
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.beneficiary_repository import BeneficiaryRepository
from remitx_api.repositories.kyc_application_repository import KycApplicationRepository
from remitx_api.repositories.stokvel_contribution_repository import (
    StokvelContributionRepository,
)
from remitx_api.repositories.stokvel_cycle_repository import StokvelCycleRepository
from remitx_api.repositories.stokvel_invitation_repository import (
    StokvelInvitationRepository,
)
from remitx_api.repositories.stokvel_member_repository import StokvelMemberRepository
from remitx_api.repositories.stokvel_payout_repository import StokvelPayoutRepository
from remitx_api.repositories.stokvel_repository import StokvelRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services.exchange_rate_service import RateUnavailableError
from remitx_api.services.quote_service import round_amount, token_rates, token_to_fiat

# `stokvels.contribution_amount` is Numeric(20, 8). A new stokvel reports the
# amount the way the column stores it, so POST and GET print it alike.
AMOUNT_QUANTUM = Decimal("0.00000001")


def _amount(value: Decimal) -> Decimal:
    return value.quantize(AMOUNT_QUANTUM)


@dataclass(frozen=True)
class StokvelView:
    stokvel_id: uuid.UUID
    name: str
    currency: str
    # Fixed UCTUSD amount for the stokvel's life (D13)
    contribution_amount: Decimal
    is_organiser: bool
    member_count: int
    max_members: int
    created_at: datetime
    deactivated_at: datetime | None


@dataclass(frozen=True)
class StokvelInvitationView:
    invitation_id: uuid.UUID
    stokvel_id: uuid.UUID
    stokvel_name: str
    currency: str
    contribution_amount: Decimal
    # None when the inviter has no first name on file
    invited_by_name: str | None
    created_at: datetime


@dataclass(frozen=True)
class StokvelListView:
    stokvels: list[StokvelView]
    invitations: list[StokvelInvitationView]


@dataclass(frozen=True)
class StokvelMemberView:
    member_id: uuid.UUID
    user_id: uuid.UUID
    # "Tendai M."; None when the member has no first name on file
    full_name: str | None
    is_organiser: bool
    is_me: bool
    joined_at: datetime


@dataclass(frozen=True)
class StokvelBeneficiaryChoiceView:
    beneficiary_id: uuid.UUID
    full_name: str | None
    payout_currency: str


@dataclass(frozen=True)
class StokvelRoundView:
    round: int
    start_time: datetime
    deadline: datetime
    payout_time: datetime
    recipient_member_id: uuid.UUID | None
    release_status: str | None
    # None until a remittance exists. The column is `pending` from the row's
    # insert, which the screen would read as "sending".
    remittance_status: str | None
    remittance_id: uuid.UUID | None
    release_tx_hash: str | None
    burn_tx_hash: str | None


@dataclass(frozen=True)
class StokvelCycleView:
    cycle_id: uuid.UUID
    cycle_number: int
    status: str
    current_round: int | None
    total_rounds: int | None
    started_at: datetime | None
    closed_at: datetime | None
    payout_order: list[uuid.UUID]
    rounds: list[StokvelRoundView]


@dataclass(frozen=True)
class StokvelDetailContributionView:
    contribution_id: uuid.UUID
    cycle_id: uuid.UUID
    round: int
    member_id: uuid.UUID
    amount_fiat: Decimal
    amount_token: Decimal
    # The caller's own fee. None on every other member's row: that fee leg
    # sits on their account, which this caller cannot read.
    fee_amount: Decimal | None
    status: str
    evm_tx_hash: str | None
    created_at: datetime


@dataclass(frozen=True)
class StokvelDetailInvitationView:
    invitation_id: uuid.UUID
    stokvel_id: uuid.UUID
    invitee_name: str | None
    account_reference: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class StokvelDetailView:
    stokvel: StokvelView
    organiser_name: str | None
    contribution_fiat_estimate: Decimal | None
    phase: str
    current_round: int | None
    total_rounds: int | None
    next_payout_time: datetime | None
    my_contribution_status: str | None
    my_member_id: uuid.UUID
    my_beneficiary: StokvelBeneficiaryChoiceView | None
    members: list[StokvelMemberView]
    invitations: list[StokvelDetailInvitationView]
    cycle: StokvelCycleView | None
    contributions: list[StokvelDetailContributionView]


def stokvel_view(
    stokvel: Stokvel, user_id: uuid.UUID, *, member_count: int
) -> StokvelView:
    """`stokvel` as `user_id` sees it. Shared with accepting an invitation,
    which answers with the stokvel just joined."""
    return StokvelView(
        stokvel_id=stokvel.id,
        name=stokvel.name,
        currency=stokvel.currency,
        contribution_amount=_amount(stokvel.contribution_amount),
        is_organiser=stokvel.organiser_user_id == user_id,
        member_count=member_count,
        max_members=Config().MAX_STOKVEL_MEMBERS,
        created_at=stokvel.created_at,
        deactivated_at=stokvel.deactivated_at,
    )


def open_forming_cycle(stokvel: Stokvel) -> StokvelCycle:
    """Open the stokvel's first cycle as `forming`, with an empty row for
    each current member, and make it the stokvel's current cycle. Only the
    Organiser may insert a cycle under row-level security.

    Cycle 1 only: the next cycle after one closes is #237's.
    """
    cycles = StokvelCycleRepository()
    cycle = cycles.add_forming_cycle(stokvel.id, cycle_number=1)
    for member in StokvelMemberRepository().list_active(stokvel.id):
        cycles.add_cycle_member(cycle.id, member.id)
    stokvel.current_cycle_id = cycle.id
    return cycle


class StokvelController:
    def __init__(self) -> None:
        self._accounts = AccountRepository()
        self._applications = KycApplicationRepository()
        self._stokvels = StokvelRepository()
        self._members = StokvelMemberRepository()
        self._invitations = StokvelInvitationRepository()
        self._cycles = StokvelCycleRepository()
        self._contributions = StokvelContributionRepository()
        self._payouts = StokvelPayoutRepository()
        self._transactions = TransactionRepository()
        self._users = UserRepository()
        self._beneficiaries = BeneficiaryRepository()

    @db_transaction
    def create_stokvel(
        self,
        user_id: uuid.UUID,
        name: str,
        currency: str,
        contribution_amount: Decimal,
    ) -> StokvelView:
        """Create a stokvel with the caller as its Organiser and first Member.

        One transaction: the stokvel, its `STOKVEL` ledger account (D9), the
        Organiser's membership, paid from their own fiat account in the
        Stokvel currency, and its first cycle, `forming`. Nothing goes
        on-chain yet: `createStokvel` is sent when the first cycle starts.
        """
        if not self._applications.get_standing(user_id).is_verified:
            raise KycNotApprovedToCreateStokvelError()
        account = self._accounts.get_user_account(user_id, currency)
        if account is None:
            raise StokvelCurrencyAccountMissingError(currency)

        stokvel = self._stokvels.add(
            Stokvel(
                organiser_user_id=user_id,
                name=name,
                currency=currency,
                contribution_amount=contribution_amount,
            )
        )
        self._accounts.create_stokvel_account(stokvel)
        self._members.add(
            StokvelMember(
                stokvel_id=stokvel.id,
                user_id=user_id,
                account_id=account.account_id,
                invitation_id=None,
            )
        )
        open_forming_cycle(stokvel)
        return stokvel_view(stokvel, user_id, member_count=1)

    def list_stokvels(self, user_id: uuid.UUID) -> StokvelListView:
        """The stokvels the caller is a current member of, and their pending
        invitations, each newest first."""
        return StokvelListView(
            stokvels=[
                stokvel_view(stokvel, user_id, member_count=member_count)
                for stokvel, member_count in self._stokvels.list_for_member(user_id)
            ],
            invitations=[
                StokvelInvitationView(
                    invitation_id=invitation.id,
                    stokvel_id=stokvel.id,
                    stokvel_name=stokvel.name,
                    currency=stokvel.currency,
                    contribution_amount=_amount(stokvel.contribution_amount),
                    invited_by_name=short_display_name(
                        inviter.first_name, inviter.last_name
                    ),
                    created_at=invitation.created_at,
                )
                for invitation, stokvel, inviter in (
                    self._invitations.list_pending_for_invitee(user_id)
                )
            ],
        )

    def get_stokvel(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID
    ) -> StokvelDetailView:
        """Everything the member screen shows for one stokvel. A caller who
        is not a current member gets the same 404 as an unknown id.

        The fiat estimate is today's rate and may be missing when no rate is
        available; the rest of the screen still loads. A rate lookup can
        commit, so it runs before the reads that build the view."""
        stokvel, member = self._visible_stokvel(user_id, stokvel_id)
        estimate = _fiat_estimate(stokvel.currency, stokvel.contribution_amount)
        stokvel, member = self._visible_stokvel(user_id, stokvel_id)

        members = self._members.list_active(stokvel.id)
        users = self._users.get_many(
            {row.user_id for row in members} | {stokvel.organiser_user_id}
        )
        cycle = (
            self._cycles.get_by_id(stokvel.current_cycle_id)
            if stokvel.current_cycle_id is not None
            else None
        )
        if cycle is None:
            cycle_view, contributions, beneficiary = None, [], None
        else:
            cycle_view, contributions, beneficiary = self._cycle_view(cycle, member.id)
        current_round = cycle.current_round if cycle is not None else None
        return StokvelDetailView(
            stokvel=stokvel_view(stokvel, user_id, member_count=len(members)),
            organiser_name=_display(users.get(stokvel.organiser_user_id)),
            contribution_fiat_estimate=estimate,
            phase=cycle.status if cycle is not None else "forming",
            current_round=current_round,
            total_rounds=cycle.total_rounds if cycle is not None else None,
            next_payout_time=_next_payout_time(cycle_view, current_round),
            my_contribution_status=_my_status(contributions, member.id, current_round),
            my_member_id=member.id,
            my_beneficiary=beneficiary,
            members=[
                StokvelMemberView(
                    member_id=row.id,
                    user_id=row.user_id,
                    full_name=_display(users.get(row.user_id)),
                    is_organiser=row.user_id == stokvel.organiser_user_id,
                    is_me=row.user_id == user_id,
                    joined_at=row.joined_at,
                )
                for row in members
            ],
            invitations=[
                StokvelDetailInvitationView(
                    invitation_id=invitation.id,
                    stokvel_id=invitation.stokvel_id,
                    invitee_name=_display(invitee),
                    account_reference=reference or "",
                    status=invitation.status,
                    created_at=invitation.created_at,
                )
                for invitation, invitee, reference in (
                    self._invitations.list_pending_for_stokvel(
                        stokvel.id, stokvel.currency
                    )
                )
            ],
            cycle=cycle_view,
            contributions=contributions,
        )

    def _visible_stokvel(
        self, user_id: uuid.UUID, stokvel_id: uuid.UUID
    ) -> tuple[Stokvel, StokvelMember]:
        """The stokvel and the caller's current membership. Both misses are
        one 404, so an id reveals nothing. Scoped here, not only by
        row-level security, so SQLite returns the same answer."""
        stokvel = self._stokvels.get_by_id(stokvel_id)
        member = (
            self._members.get_active_member(stokvel_id, user_id)
            if stokvel is not None
            else None
        )
        if stokvel is None or member is None:
            raise StokvelNotFoundError()
        return stokvel, member

    def _cycle_view(
        self, cycle: StokvelCycle, my_member_id: uuid.UUID
    ) -> tuple[
        StokvelCycleView,
        list[StokvelDetailContributionView],
        StokvelBeneficiaryChoiceView | None,
    ]:
        cycle_members = self._cycles.get_cycle_members(cycle.id)
        rounds = self._cycles.get_cycle_rounds(cycle.id)
        payouts = {row.round: row for row in self._payouts.get_cycle_payouts(cycle.id)}
        by_position = {
            row.payout_position: row.member_id
            for row in cycle_members
            if row.payout_position is not None
        }
        contributions = self._contributions.list_for_cycle(cycle.id)
        fees = self._transactions.amounts(
            {
                row.fee_tx_id
                for row in contributions
                if row.member_id == my_member_id and row.fee_tx_id is not None
            }
        )
        return (
            StokvelCycleView(
                cycle_id=cycle.id,
                cycle_number=cycle.cycle_number,
                status=cycle.status,
                current_round=cycle.current_round,
                total_rounds=cycle.total_rounds,
                started_at=cycle.started_at,
                closed_at=cycle.closed_at,
                payout_order=_payout_order(by_position),
                rounds=[
                    _round_view(rnd, by_position.get(rnd.round), payouts.get(rnd.round))
                    for rnd in rounds
                ],
            ),
            [
                StokvelDetailContributionView(
                    contribution_id=row.id,
                    cycle_id=row.cycle_id,
                    round=row.round,
                    member_id=row.member_id,
                    amount_fiat=round_amount(row.amount_fiat),
                    amount_token=_amount(row.amount_token),
                    fee_amount=_fee_amount(fees, row, my_member_id),
                    status=row.status,
                    evm_tx_hash=row.evm_tx_hash,
                    created_at=row.created_at,
                )
                for row in contributions
            ],
            _my_beneficiary(
                cycle_members, my_member_id, self._beneficiaries, self._users
            ),
        )


def _fee_amount(
    fees: dict[uuid.UUID, Decimal], row, my_member_id: uuid.UUID
) -> Decimal | None:
    if row.member_id != my_member_id or row.fee_tx_id is None:
        return None
    amount = fees.get(row.fee_tx_id)
    return None if amount is None else round_amount(amount)


def _display(user: User | None) -> str | None:
    return None if user is None else short_display_name(user.first_name, user.last_name)


def _fiat_estimate(currency: str, amount: Decimal) -> Decimal | None:
    try:
        return token_to_fiat(amount, token_rates(currency))
    except RateUnavailableError:
        return None


def _payout_order(by_position: dict[int, uuid.UUID]) -> list[uuid.UUID]:
    """Member ids from position 0 upward, stopping at the first gap."""
    order: list[uuid.UUID] = []
    position = 0
    while position in by_position:
        order.append(by_position[position])
        position += 1
    return order


def _next_payout_time(
    cycle: StokvelCycleView | None, current_round: int | None
) -> datetime | None:
    if cycle is None or current_round is None:
        return None
    rnd = next((row for row in cycle.rounds if row.round == current_round), None)
    return None if rnd is None else rnd.payout_time


def _my_status(
    contributions: list[StokvelDetailContributionView],
    member_id: uuid.UUID,
    current_round: int | None,
) -> str | None:
    if current_round is None:
        return None
    return next(
        (
            row.status
            for row in contributions
            if row.member_id == member_id
            and row.round == current_round
            and row.status != STATUS_FAILED
        ),
        None,
    )


def _round_view(
    rnd: StokvelRound,
    recipient_member_id: uuid.UUID | None,
    payout: StokvelPayout | None,
) -> StokvelRoundView:
    sent = payout is not None and payout.remittance_id is not None
    return StokvelRoundView(
        round=rnd.round,
        start_time=rnd.start_time,
        deadline=rnd.deadline,
        payout_time=rnd.payout_time,
        recipient_member_id=recipient_member_id,
        release_status=None if payout is None else payout.release_status,
        remittance_status=payout.remittance_status if sent else None,
        remittance_id=None if payout is None else payout.remittance_id,
        release_tx_hash=None if payout is None else payout.release_tx_hash,
        burn_tx_hash=None if payout is None else payout.burn_tx_hash,
    )


def _my_beneficiary(
    cycle_members: list[StokvelCycleMember],
    my_member_id: uuid.UUID,
    beneficiaries: BeneficiaryRepository,
    users: UserRepository,
) -> StokvelBeneficiaryChoiceView | None:
    row = next(
        (member for member in cycle_members if member.member_id == my_member_id),
        None,
    )
    if row is None or row.payout_beneficiary_id is None or row.payout_currency is None:
        return None
    beneficiary = beneficiaries.get_by_id(row.payout_beneficiary_id)
    if beneficiary is None:
        return None
    return StokvelBeneficiaryChoiceView(
        beneficiary_id=beneficiary.beneficiary_id,
        full_name=_display(users.get_by_id(beneficiary.linked_user_id)),
        payout_currency=row.payout_currency,
    )
