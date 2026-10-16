import uuid

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.repositories.repository import Repository


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
