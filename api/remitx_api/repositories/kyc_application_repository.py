import uuid
from dataclasses import dataclass

from sqlalchemy import select

from remitx_api.extensions import db
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_lifecycle import (
    KYC_TIER_NONE,
    OPEN_STATUSES,
    VERIFIED_STATUSES,
    KycStatus,
)
from remitx_api.repositories.repository import Repository


@dataclass(frozen=True)
class KycStanding:
    """Where a user stands, derived from their applications rather than stored.

    `users` carries no `kyc_status` column: one authoritative place for KYC
    state beats a copy that can fall out of step with it. The cost is that
    callers who need a user's status — the limits check on every quote, the
    profile page — read it through here instead of off the user row.
    """

    status: KycStatus
    tier: int
    application_id: uuid.UUID | None

    @property
    def is_verified(self) -> bool:
        return self.status in VERIFIED_STATUSES


class KycApplicationRepository(Repository[KycApplication, uuid.UUID]):
    """Reads only.

    Every write to a KYC application is part of a multi-table transition — the
    application row and its `kyc_decisions` row — and `Repository.save` commits
    internally, so a transition built out of repository calls would commit in
    pieces. `KycController.transition` uses `db.session` directly instead
    (CLAUDE.md).
    """

    def __init__(self) -> None:
        super().__init__(KycApplication)

    def get_open_for_user(self, user_id: uuid.UUID) -> KycApplication | None:
        """The application this user currently has in flight, if any.

        At most one can exist — `uq_kyc_applications_one_open_per_user` is what
        guarantees that, not this query.
        """
        return db.session.scalars(
            select(KycApplication)
            .where(KycApplication.user_id == user_id)
            .where(KycApplication.status.in_(status.value for status in OPEN_STATUSES))
        ).first()

    def get_latest_for_user(self, user_id: uuid.UUID) -> KycApplication | None:
        """This user's most recent attempt, whatever state it is in."""
        return db.session.scalars(
            select(KycApplication)
            .where(KycApplication.user_id == user_id)
            .order_by(KycApplication.created_at.desc())
        ).first()

    def get_standing(self, user_id: uuid.UUID) -> KycStanding:
        """A user's KYC status and limit tier, derived from their applications.

        The status is their latest attempt's, or `not_started` when they have
        never made one.

        The tier comes from their latest *standing* verification (`approved` or
        `review_due`), which is not always the latest attempt: an approved user
        who opens a refresh application keeps their allowance while it is in
        flight, rather than dropping to zero for the duration. A later rejected
        attempt does not revoke an earlier approval either — stopping an
        already-verified user is what `users.suspended_at` is for.
        """
        latest = self.get_latest_for_user(user_id)
        if latest is None:
            return KycStanding(
                status=KycStatus.NOT_STARTED,
                tier=KYC_TIER_NONE,
                application_id=None,
            )

        verified = db.session.scalars(
            select(KycApplication)
            .where(KycApplication.user_id == user_id)
            .where(
                KycApplication.status.in_(status.value for status in VERIFIED_STATUSES)
            )
            .order_by(KycApplication.created_at.desc())
        ).first()

        return KycStanding(
            status=KycStatus(latest.status),
            tier=(
                KYC_TIER_NONE
                if verified is None or verified.tier_granted is None
                else verified.tier_granted
            ),
            application_id=latest.application_id,
        )

    def list_for_user(self, user_id: uuid.UUID) -> list[KycApplication]:
        """Every attempt this user has made, newest first."""
        return list(
            db.session.scalars(
                select(KycApplication)
                .where(KycApplication.user_id == user_id)
                .order_by(KycApplication.created_at.desc())
            ).all()
        )

    def list_decisions(self, application_id: uuid.UUID) -> list[KycDecision]:
        """One application's decision history, oldest first."""
        return list(
            db.session.scalars(
                select(KycDecision)
                .where(KycDecision.application_id == application_id)
                .order_by(KycDecision.decided_at, KycDecision.decision_id)
            ).all()
        )
