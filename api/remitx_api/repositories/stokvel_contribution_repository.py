import uuid
from decimal import Decimal

from sqlalchemy import and_, case, func, select

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.repositories.remittance_repository import CENTS, SentTotals
from remitx_api.repositories.repository import Repository
from remitx_api.services.send_limits import LimitWindows

_FAILED = StokvelContributionStatus.FAILED.value


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

    def contributed_zar(self, user_id: uuid.UUID, windows: LimitWindows) -> SentTotals:
        """What the user contributed to stokvels during `windows`' day and
        month, in rand, fee included (`amount_zar`), by when each contribution
        was made. Every contribution that has not failed counts, pending ones
        too, as `RemittanceRepository.sent_zar` counts unsettled sends: a
        contribution counts toward the member's own limits (D8)."""
        in_day = and_(
            StokvelContribution.created_at >= windows.day_start,
            StokvelContribution.created_at < windows.day_end,
        )
        amount = func.coalesce(StokvelContribution.amount_zar, 0)
        day_total, month_total = db.session.execute(
            select(
                func.coalesce(func.sum(case((in_day, amount), else_=0)), 0),
                func.coalesce(func.sum(amount), 0),
            )
            .select_from(StokvelContribution)
            .join(StokvelMember, StokvelMember.id == StokvelContribution.member_id)
            .where(
                StokvelMember.user_id == user_id,
                StokvelContribution.status != _FAILED,
                StokvelContribution.created_at >= windows.month_start,
                StokvelContribution.created_at < windows.month_end,
            )
        ).one()
        # SQLite sums Numeric columns as floats.
        return SentTotals(
            day_zar=Decimal(str(day_total)).quantize(CENTS),
            month_zar=Decimal(str(month_total)).quantize(CENTS),
        )
