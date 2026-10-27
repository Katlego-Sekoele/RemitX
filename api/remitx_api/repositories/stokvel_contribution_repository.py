import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.repositories.remittance_repository import CENTS
from remitx_api.repositories.repository import Repository
from remitx_api.services.send_limits import LimitWindows

_FAILED = StokvelContributionStatus.FAILED.value


def _as_utc(value: datetime) -> datetime:
    """SQLite returns timestamps without their zone; they are stored UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class UnpaidRound:
    """A round a member still owes their contribution to, with what pricing
    that contribution needs (`StokvelContributionRepository.unpaid_rounds`)."""

    stokvel_id: uuid.UUID
    cycle_id: uuid.UUID
    round: int
    # Pay-by date: it decides the month the contribution is reserved in
    deadline: datetime
    currency: str
    contribution_amount: Decimal
    member_count: int
    payout_currency: str


class StokvelContributionRepository(Repository[StokvelContribution, uuid.UUID]):
    """Repository for stokvel contributions. Queries here run under row-level
    security on Postgres; SQLite (tests) does not filter, so callers scope by
    user. The contribution API (R2-11) and its worker tasks (R2-12) add the
    writes."""

    def __init__(self) -> None:
        super().__init__(StokvelContribution)

    def get_member_contribution(
        self, cycle_id: uuid.UUID, round_: int, member_id: uuid.UUID
    ) -> StokvelContribution | None:
        """The member's contribution to the round that has not failed, if any.
        There is at most one (uq_stokvel_contributions_once)."""
        return db.session.scalars(
            select(StokvelContribution).where(
                StokvelContribution.cycle_id == cycle_id,
                StokvelContribution.round == round_,
                StokvelContribution.member_id == member_id,
                StokvelContribution.status != StokvelContributionStatus.FAILED.value,
            )
        ).one_or_none()

    def list_for_cycle(self, cycle_id: uuid.UUID) -> list[StokvelContribution]:
        """Every contribution in the cycle, failed attempts included, in
        round order then oldest first."""
        return list(
            db.session.scalars(
                select(StokvelContribution)
                .where(StokvelContribution.cycle_id == cycle_id)
                .order_by(
                    StokvelContribution.round,
                    StokvelContribution.created_at,
                    StokvelContribution.id,
                )
            ).all()
        )

    def get_round_contributions(
        self, cycle_id: uuid.UUID, round_: int
    ) -> list[StokvelContribution]:
        """Every contribution to a round, failed attempts included, oldest
        first."""
        return list(
            db.session.scalars(
                select(StokvelContribution)
                .where(
                    StokvelContribution.cycle_id == cycle_id,
                    StokvelContribution.round == round_,
                )
                .order_by(StokvelContribution.created_at, StokvelContribution.id)
            ).all()
        )

    def get_paid_member_ids(self, cycle_id: uuid.UUID, round_: int) -> set[uuid.UUID]:
        """The members whose contribution to the round is confirmed on-chain.
        Who has paid is derived from these rows, never stored."""
        return set(
            db.session.scalars(
                select(StokvelContribution.member_id).where(
                    StokvelContribution.cycle_id == cycle_id,
                    StokvelContribution.round == round_,
                    StokvelContribution.status
                    == StokvelContributionStatus.CONFIRMED.value,
                )
            ).all()
        )

    def open_round(
        self, cycle_id: uuid.UUID, *, member_count: int, total_rounds: int
    ) -> int | None:
        """The round a contribution goes into now: the first round with fewer
        contributions that have not failed than the cycle has members, the
        same rule as the contract's `openRound` (rounds fill in order, and a
        pending contribution holds its place). None once every round has one
        from every member."""
        counts = dict(
            db.session.execute(
                select(StokvelContribution.round, func.count())
                .where(
                    StokvelContribution.cycle_id == cycle_id,
                    StokvelContribution.status != _FAILED,
                )
                .group_by(StokvelContribution.round)
            ).all()
        )
        for round_ in range(total_rounds):
            if counts.get(round_, 0) < member_count:
                return round_
        return None

    def contributed_zar(self, user_id: uuid.UUID, windows: LimitWindows) -> Decimal:
        """What the user contributed to stokvels during `windows`' month, in
        rand, fee included (`amount_zar`), by when each contribution was made.
        Every contribution that has not failed counts, pending ones too, as
        `RemittanceRepository.sent_zar` counts unsettled sends: a contribution
        counts toward the member's own monthly limit, never the daily one
        (D8)."""
        total = db.session.scalar(
            select(func.coalesce(func.sum(StokvelContribution.amount_zar), 0))
            .select_from(StokvelContribution)
            .join(StokvelMember, StokvelMember.id == StokvelContribution.member_id)
            .where(
                StokvelMember.user_id == user_id,
                StokvelContribution.status != _FAILED,
                StokvelContribution.created_at >= windows.month_start,
                StokvelContribution.created_at < windows.month_end,
            )
        )
        # SQLite sums Numeric columns as floats.
        return Decimal(str(total)).quantize(CENTS)

    def unpaid_rounds(self, user_id: uuid.UUID) -> list[UnpaidRound]:
        """Every round the user still owes a contribution to: the rounds of
        each active cycle they are locked into, as a current member, that
        have no contribution from them that has not failed. A pending
        contribution has paid its round here, as it counts as used.

        Each comes with what pricing it needs: the stokvel's currency and
        token amount, the cycle's member count, and the payout currency of
        the member the round pays (which sets the fee share). Leaving the
        stokvel or the cycle closing drops its rounds."""
        mine = (
            select(
                StokvelCycleMember.cycle_id,
                StokvelCycleMember.member_id,
                Stokvel.id.label("stokvel_id"),
                Stokvel.currency,
                Stokvel.contribution_amount,
            )
            .join(StokvelMember, StokvelMember.id == StokvelCycleMember.member_id)
            .join(StokvelCycle, StokvelCycle.id == StokvelCycleMember.cycle_id)
            .join(Stokvel, Stokvel.id == StokvelCycle.stokvel_id)
            .where(
                StokvelMember.user_id == user_id,
                StokvelMember.left_at.is_(None),
                StokvelCycleMember.locked.is_(True),
                StokvelCycle.status == StokvelCycleStatus.ACTIVE.value,
            )
        )
        places = db.session.execute(mine).all()
        if not places:
            return []
        cycle_ids = [place.cycle_id for place in places]
        member_ids = [place.member_id for place in places]

        # Who each round pays, and so in what currency, and how many pay in.
        payout_currency: dict[tuple[uuid.UUID, int], str | None] = {}
        member_count: dict[uuid.UUID, int] = {}
        for cycle_id, position, currency in db.session.execute(
            select(
                StokvelCycleMember.cycle_id,
                StokvelCycleMember.payout_position,
                StokvelCycleMember.payout_currency,
            ).where(
                StokvelCycleMember.cycle_id.in_(cycle_ids),
                StokvelCycleMember.locked.is_(True),
            )
        ).all():
            payout_currency[(cycle_id, position)] = currency
            member_count[cycle_id] = member_count.get(cycle_id, 0) + 1

        paid = set(
            db.session.execute(
                select(StokvelContribution.cycle_id, StokvelContribution.round).where(
                    StokvelContribution.cycle_id.in_(cycle_ids),
                    StokvelContribution.member_id.in_(member_ids),
                    StokvelContribution.status != _FAILED,
                )
            ).all()
        )
        by_cycle = {place.cycle_id: place for place in places}
        rounds = db.session.execute(
            select(StokvelRound.cycle_id, StokvelRound.round, StokvelRound.deadline)
            .where(StokvelRound.cycle_id.in_(cycle_ids))
            .order_by(StokvelRound.deadline, StokvelRound.round)
        ).all()
        return [
            UnpaidRound(
                stokvel_id=by_cycle[cycle_id].stokvel_id,
                cycle_id=cycle_id,
                round=round_,
                deadline=_as_utc(deadline),
                currency=by_cycle[cycle_id].currency,
                contribution_amount=by_cycle[cycle_id].contribution_amount,
                member_count=member_count[cycle_id],
                payout_currency=(
                    payout_currency.get((cycle_id, round_))
                    or by_cycle[cycle_id].currency
                ),
            )
            for cycle_id, round_, deadline in rounds
            if (cycle_id, round_) not in paid
        ]
