"""The one place a KYC application's status changes.

Every status change in the system goes through `KycController.transition`.
Assigning `application.status` anywhere else is a bug: it skips the legality
check, the `kyc_decisions` row, and the version bump that stops one reviewer
overwriting another.

Why a controller and not a repository method: a transition writes two tables
and either all of it lands or none of it does. `Repository.save` commits
internally (CLAUDE.md), so a transition assembled from repository calls would
commit the application row before the decision row existed — and a failure in
between would leave an approved applicant with no record of who approved them.
This talks to `db.session` directly and commits exactly once.

There is no denormalised `users.kyc_status` to keep in step; a user's standing
is derived on read by `KycApplicationRepository.get_standing`.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from remitx_api.errors.kyc import (
    IllegalKycTransitionError,
    KycVersionConflictError,
    OpenApplicationExistsError,
    UnknownKycApplicationError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_lifecycle import (
    DECISION_STATUSES,
    KYC_TIER_VERIFIED,
    LEGAL_TRANSITIONS,
    REVIEW_INTERVAL_DAYS,
    KycReasonCode,
    KycRiskRating,
    KycStatus,
)
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
    KycStanding,
)
from remitx_api.repositories.user_repository import UserRepository


def utcnow() -> datetime:
    return datetime.now(UTC)


class KycController:
    def __init__(self) -> None:
        self._applications = KycApplicationRepository()
        self._users = UserRepository()

    def get_standing(self, user_id: uuid.UUID) -> KycStanding:
        """Where this user stands, derived from their applications."""
        return self._applications.get_standing(user_id)

    def start_application(self, user_id: uuid.UUID) -> KycApplication:
        """Open a fresh attempt for a user, in the `in_progress` draft state.

        This — not a transition — is how a user leaves `not_started`,
        `rejected` or `review_due`: those attempts keep the data they were
        decided on, so the next attempt is a new row. See
        models/orm/kyc_lifecycle.py.
        """
        self._users.require_by_id(user_id)

        existing = self._applications.get_open_for_user(user_id)
        if existing is not None:
            raise OpenApplicationExistsError(
                f"User {user_id} already has application {existing.application_id} "
                f"in flight ({existing.status})"
            )

        application = KycApplication(
            user_id=user_id,
            status=KycStatus.IN_PROGRESS.value,
        )
        db.session.add(application)
        try:
            db.session.commit()
        except IntegrityError as exc:
            # A concurrent request won the race for this user's one open slot.
            # The read above cannot see it; uq_kyc_applications_one_open_per_user
            # can, which is why the constraint is in the database and not here.
            db.session.rollback()
            raise OpenApplicationExistsError(
                f"User {user_id} already has an application in flight"
            ) from exc
        return application

    def transition(
        self,
        application_id: uuid.UUID,
        to_status: KycStatus | str,
        *,
        expected_version: int,
        actor_user_id: uuid.UUID | None = None,
        reason_code: KycReasonCode | str | None = None,
        reason_text: str | None = None,
        risk_rating: KycRiskRating | str | None = None,
        tier_granted: int | None = None,
    ) -> KycApplication:
        """Move one application to `to_status`, or raise.

        Illegal moves raise `IllegalKycTransitionError` — they never silently
        no-op, because a reviewer who clicks Approve on an already-rejected
        application needs to be told, not ignored.

        `expected_version` is the version the caller was shown. The update
        touches only a row still at that version, so of two reviewers who both
        opened the detail page, the second gets `KycVersionConflictError` (409)
        instead of overwriting the first's decision.

        The status change and the `kyc_decisions` row that records who made it
        land in one transaction, or neither does.
        """
        to_status = self._as_status(to_status)

        application = db.session.get(KycApplication, application_id)
        if application is None:
            raise UnknownKycApplicationError(str(application_id))

        from_status = self._as_status(application.status)
        if to_status not in LEGAL_TRANSITIONS[from_status]:
            raise IllegalKycTransitionError(
                f"Cannot move application {application_id} from "
                f"{from_status.value} to {to_status.value}"
            )

        is_decision = to_status in DECISION_STATUSES
        if is_decision and actor_user_id is None:
            # A compliance log whose `decided_by_user_id` is NULL because the
            # caller forgot to pass one is worse than no log: it reads as
            # "the system did this".
            raise ValueError(
                f"Moving an application to {to_status.value} is a reviewer "
                "decision and requires actor_user_id"
            )

        now = utcnow()
        changes: dict = {
            "status": to_status.value,
            "version": expected_version + 1,
            "updated_at": now,
        }
        if risk_rating is not None:
            changes["risk_rating"] = KycRiskRating(risk_rating).value
        if to_status is KycStatus.SUBMITTED and application.submitted_at is None:
            # First submission only: a more_info_required round trip comes back
            # through here, and the original submission time is the one that
            # matters for turnaround reporting.
            changes["submitted_at"] = now
        if to_status is KycStatus.APPROVED:
            changes["tier_granted"] = (
                KYC_TIER_VERIFIED if tier_granted is None else tier_granted
            )
            changes["next_review_at"] = now + timedelta(days=REVIEW_INTERVAL_DAYS)

        try:
            # Conditional on the version, so losing the race means updating
            # zero rows rather than clobbering the winner.
            result = db.session.execute(
                update(KycApplication)
                .where(KycApplication.application_id == application_id)
                .where(KycApplication.version == expected_version)
                .values(**changes)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount == 0:
                raise KycVersionConflictError(
                    f"Application {application_id} is no longer at version "
                    f"{expected_version}; reload it and decide again"
                )

            if is_decision:
                db.session.add(
                    KycDecision(
                        application_id=application_id,
                        decision=to_status.value,
                        from_status=from_status.value,
                        reason_code=(
                            None
                            if reason_code is None
                            else KycReasonCode(reason_code).value
                        ),
                        reason_text=reason_text,
                        decided_by_user_id=actor_user_id,
                        decided_at=now,
                    )
                )

            db.session.commit()
        except Exception:
            # Includes the version conflict: rolling back is what makes "all of
            # it or none of it" true, and leaves the session usable so the route
            # can serve the 409.
            db.session.rollback()
            raise

        return application

    @staticmethod
    def _as_status(value: KycStatus | str) -> KycStatus:
        try:
            return KycStatus(value)
        except ValueError as exc:
            raise IllegalKycTransitionError(f"Unknown KYC status: {value!r}") from exc
