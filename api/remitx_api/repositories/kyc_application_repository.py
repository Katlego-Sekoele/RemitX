import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from remitx_api.db.transaction import db_transaction
from remitx_api.errors.kyc import (
    IllegalKycTransitionError,
    KycVersionConflictError,
    OpenApplicationExistsError,
    UnknownKycApplicationError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_application_history import KycApplicationHistory
from remitx_api.models.orm.kyc_decision import KycDecision
from remitx_api.models.orm.kyc_decision_history import KycDecisionHistory
from remitx_api.models.orm.kyc_lifecycle import (
    DECISION_STATUSES,
    KYC_TIER_NONE,
    KYC_TIER_VERIFIED,
    OPEN_STATUSES,
    REVIEW_INTERVAL_DAYS,
    VERIFIED_STATUSES,
    KycReasonCode,
    KycRiskRating,
    KycStatus,
)
from remitx_api.repositories.kyc_status_progression_repository import (
    KycApplicationStatusProgressionRepository,
)
from remitx_api.repositories.repository import Repository


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class KycStanding:
    """Where a user stands, derived from their applications rather than stored."""

    status: KycStatus
    tier: int
    application_id: uuid.UUID | None

    @property
    def is_verified(self) -> bool:
        return self.status in VERIFIED_STATUSES


class KycApplicationRepository(Repository[KycApplication, uuid.UUID]):
    def __init__(self) -> None:
        super().__init__(KycApplication)
        self._progressions = KycApplicationStatusProgressionRepository()

    def get_open_for_user(self, user_id: uuid.UUID) -> KycApplication | None:
        return db.session.scalars(
            select(KycApplication)
            .where(KycApplication.user_id == user_id)
            .where(KycApplication.status.in_(status.value for status in OPEN_STATUSES))
        ).first()

    def get_latest_for_user(self, user_id: uuid.UUID) -> KycApplication | None:
        return db.session.scalars(
            select(KycApplication)
            .where(KycApplication.user_id == user_id)
            .order_by(KycApplication.created_at.desc())
        ).first()

    def get_standing(self, user_id: uuid.UUID) -> KycStanding:
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
        return list(
            db.session.scalars(
                select(KycApplication)
                .where(KycApplication.user_id == user_id)
                .order_by(KycApplication.created_at.desc())
            ).all()
        )

    def list_decisions(self, application_id: uuid.UUID) -> list[KycDecision]:
        return list(
            db.session.scalars(
                select(KycDecision)
                .where(KycDecision.application_id == application_id)
                .order_by(KycDecision.decided_at, KycDecision.decision_id)
            ).all()
        )

    def list_history(self, application_id: uuid.UUID) -> list[KycDecisionHistory]:
        return list(
            db.session.scalars(
                select(KycDecisionHistory)
                .where(KycDecisionHistory.application_id == application_id)
                .order_by(KycDecisionHistory.made_at, KycDecisionHistory.history_id)
            ).all()
        )

    def list_application_history(
        self, application_id: uuid.UUID
    ) -> list[KycApplicationHistory]:
        return list(
            db.session.scalars(
                select(KycApplicationHistory)
                .where(KycApplicationHistory.application_id == application_id)
                .order_by(
                    KycApplicationHistory.changed_at,
                    KycApplicationHistory.history_id,
                )
            ).all()
        )

    @db_transaction
    def create_open_application(self, user_id: uuid.UUID) -> KycApplication:
        existing = self.get_open_for_user(user_id)
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
            db.session.flush()
        except IntegrityError as exc:
            raise OpenApplicationExistsError(
                f"User {user_id} already has an application in flight"
            ) from exc

        db.session.add(
            KycApplicationHistory(
                application_id=application.application_id,
                status=KycStatus.IN_PROGRESS.value,
                version_after=application.version,
                changed_at=application.created_at,
            )
        )
        return application

    @db_transaction
    def apply_transition(
        self,
        application_id: uuid.UUID,
        to_status: KycStatus,
        *,
        expected_version: int,
        actor_user_id: uuid.UUID | None = None,
        reason_code: KycReasonCode | str | None = None,
        reason_text: str | None = None,
        risk_rating: KycRiskRating | str | None = None,
        tier_granted: int | None = None,
    ) -> KycApplication:
        application = db.session.get(KycApplication, application_id)
        if application is None:
            raise UnknownKycApplicationError(str(application_id))

        from_status = KycStatus(application.status)
        if not self._progressions.is_allowed(from_status.value, to_status.value):
            raise IllegalKycTransitionError(
                f"Cannot move application {application_id} from "
                f"{from_status.value} to {to_status.value}"
            )

        is_decision = to_status in DECISION_STATUSES
        if is_decision and actor_user_id is None:
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
            changes["submitted_at"] = now
        if to_status is KycStatus.APPROVED:
            changes["tier_granted"] = (
                KYC_TIER_VERIFIED if tier_granted is None else tier_granted
            )
            changes["next_review_at"] = now + timedelta(days=REVIEW_INTERVAL_DAYS)

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

        normalized_reason_code = (
            None if reason_code is None else KycReasonCode(reason_code).value
        )
        db.session.add(
            KycDecisionHistory(
                application_id=application_id,
                status=to_status.value,
                reason_code=normalized_reason_code,
                reason_text=reason_text,
                made_by_user_id=actor_user_id,
                made_at=now,
            )
        )

        db.session.add(
            KycApplicationHistory(
                application_id=application_id,
                status=to_status.value,
                version_after=expected_version + 1,
                risk_rating=changes.get("risk_rating"),
                tier_granted=changes.get("tier_granted"),
                submitted_at=changes.get("submitted_at"),
                reason_code=normalized_reason_code,
                reason_text=reason_text,
                changed_by_user_id=actor_user_id,
                changed_at=now,
            )
        )

        if is_decision:
            db.session.add(
                KycDecision(
                    application_id=application_id,
                    decision=to_status.value,
                    from_status=from_status.value,
                    reason_code=normalized_reason_code,
                    reason_text=reason_text,
                    decided_by_user_id=actor_user_id,
                    decided_at=now,
                )
            )

        db.session.refresh(application)
        return application
