import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from remitx_api.clock import utcnow
from remitx_api.db.transaction import db_transaction
from remitx_api.errors.kyc import (
    IllegalKycTransitionError,
    KycRiskOverrideNotAllowedError,
    KycRiskRulesMisconfiguredError,
    KycVersionConflictError,
    OpenApplicationExistsError,
    UnknownKycApplicationError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_application_history import KycApplicationHistory
from remitx_api.models.orm.kyc_application_risk_view import kyc_application_risk
from remitx_api.models.orm.kyc_assessment_audit import KycAssessmentAudit
from remitx_api.models.orm.kyc_assessment_audit_signal import (
    KycAssessmentAuditSignal,
)
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
    KycStatus,
)
from remitx_api.models.orm.kyc_risk_rating import KycRiskRatingRecord
from remitx_api.models.orm.kyc_tier import KycTier
from remitx_api.repositories.kyc_risk_rule_repository import (
    band_from_record,
    limits_from_tier,
)
from remitx_api.repositories.kyc_status_progression_repository import (
    KycApplicationStatusProgressionRepository,
)
from remitx_api.repositories.repository import Repository
from remitx_api.services.kyc_risk_rules import RiskAssessment, allowance_for

# A rating is a reviewer's to override only while a decision is still pending.
# After approval the tier and limits already rest on it; changing it then is a
# refresh, which is a new application.
RISK_OVERRIDABLE_STATUSES = frozenset({KycStatus.SUBMITTED, KycStatus.UNDER_REVIEW})

# What the reviewer queue shows unless asked for something else: everything
# waiting on a reviewer.
QUEUE_STATUSES = (KycStatus.SUBMITTED, KycStatus.UNDER_REVIEW)


@dataclass(frozen=True)
class KycStanding:
    """Where a user stands, derived from their applications rather than stored.

    The limits are derived too — the tier's limits from `kyc_tiers`, scaled by
    the rating's `limit_percent` from `kyc_risk_ratings` — so changing either
    row changes every customer it applies to, with nothing to backfill. This
    is what the limits enforcement path (#25) reads.
    """

    status: KycStatus
    tier: int
    application_id: uuid.UUID | None
    risk_rating: str | None = None
    limit_percent: int = 100
    daily_limit_zar: Decimal = Decimal("0.00")
    monthly_limit_zar: Decimal = Decimal("0.00")

    @property
    def is_verified(self) -> bool:
        return self.status in VERIFIED_STATUSES


@dataclass(frozen=True)
class TierDecision:
    """The tier an approval grants, against the one it would have granted by
    default. `reason` is required whenever the two differ."""

    computed_tier: int
    final_tier: int
    reason: str | None = None


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
        verified = db.session.scalars(
            select(KycApplication)
            .where(KycApplication.user_id == user_id)
            .where(
                KycApplication.status.in_(status.value for status in VERIFIED_STATUSES)
            )
            .order_by(KycApplication.created_at.desc())
        ).first()

        tier_number = (
            KYC_TIER_NONE
            if verified is None or verified.tier_granted is None
            else verified.tier_granted
        )
        tier = db.session.get(KycTier, tier_number)
        if tier is None:
            raise KycRiskRulesMisconfiguredError(
                f"kyc_tiers has no tier {tier_number} to take limits from"
            )
        rating = None if verified is None else verified.effective_risk_rating
        rating_record = (
            None if rating is None else db.session.get(KycRiskRatingRecord, rating)
        )
        allowance = allowance_for(
            limits_from_tier(tier),
            None if rating_record is None else band_from_record(rating_record),
        )

        return KycStanding(
            status=(
                KycStatus.NOT_STARTED if latest is None else KycStatus(latest.status)
            ),
            tier=tier_number,
            application_id=None if latest is None else latest.application_id,
            risk_rating=rating,
            limit_percent=allowance.limit_percent,
            daily_limit_zar=allowance.daily_limit_zar,
            monthly_limit_zar=allowance.monthly_limit_zar,
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

    def list_queue(
        self,
        *,
        statuses: Iterable[KycStatus] = QUEUE_STATUSES,
        risk_rating: str | None = None,
    ) -> list[KycApplication]:
        """The reviewer queue, highest-risk first, then oldest submission first.

        Ordered and filtered through `kyc_application_risk`, so "risk" means the
        effective rating — a reviewer's override, where there is one — and
        "highest" means that rating's `severity` row, not the alphabet.
        Unscored applications sort last.
        """
        query = (
            select(KycApplication)
            .join(
                kyc_application_risk,
                kyc_application_risk.c.application_id == KycApplication.application_id,
            )
            .where(KycApplication.status.in_([status.value for status in statuses]))
            .order_by(
                func.coalesce(kyc_application_risk.c.severity, -1).desc(),
                func.coalesce(
                    KycApplication.submitted_at, KycApplication.created_at
                ).asc(),
                KycApplication.application_id,
            )
        )
        if risk_rating is not None:
            query = query.where(
                kyc_application_risk.c.effective_risk_rating == risk_rating
            )
        return list(db.session.scalars(query).all())

    def list_assessment_audit(
        self, application_id: uuid.UUID
    ) -> list[tuple[KycAssessmentAudit, list[KycAssessmentAuditSignal]]]:
        entries = list(
            db.session.scalars(
                select(KycAssessmentAudit)
                .where(KycAssessmentAudit.application_id == application_id)
                .order_by(KycAssessmentAudit.recorded_at, KycAssessmentAudit.audit_id)
            ).all()
        )
        signals: dict[uuid.UUID, list[KycAssessmentAuditSignal]] = {}
        if entries:
            for row in db.session.scalars(
                select(KycAssessmentAuditSignal)
                .where(
                    KycAssessmentAuditSignal.audit_id.in_(
                        [entry.audit_id for entry in entries]
                    )
                )
                .order_by(
                    KycAssessmentAuditSignal.score_effect.desc(),
                    KycAssessmentAuditSignal.signal,
                )
            ).all():
                signals.setdefault(row.audit_id, []).append(row)
        return [(entry, signals.get(entry.audit_id, [])) for entry in entries]

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
        previous = self.get_latest_for_user(user_id)
        if previous is not None:
            from remitx_api.repositories.kyc_onboarding_repository import (
                KycOnboardingRepository,
            )

            for field in KycOnboardingRepository().load().copy_fields:
                setattr(application, field, getattr(previous, field))
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

    def last_submitted_at(self, application_id: uuid.UUID):
        """When this application was most recently put in front of a reviewer,
        or None if it never has been. A more_info_required round trip
        resubmits, so this is the latest `submitted` history row, not the
        first-submission column."""
        return db.session.scalar(
            select(func.max(KycApplicationHistory.changed_at))
            .where(KycApplicationHistory.application_id == application_id)
            .where(KycApplicationHistory.status == KycStatus.SUBMITTED.value)
        )

    def latest_rejection_reason(self, user_id: uuid.UUID) -> str | None:
        """The reason on the most recent rejected attempt, if any.

        Shown on a resubmission so the applicant knows what to fix, without
        overwriting the rejected row.
        """
        rejected = db.session.scalars(
            select(KycApplication)
            .where(KycApplication.user_id == user_id)
            .where(KycApplication.status == KycStatus.REJECTED.value)
            .order_by(KycApplication.created_at.desc())
        ).first()
        if rejected is None:
            return None
        decision = db.session.scalars(
            select(KycDecision)
            .where(KycDecision.application_id == rejected.application_id)
            .where(KycDecision.decision == KycStatus.REJECTED.value)
            .order_by(KycDecision.decided_at.desc())
        ).first()
        if decision is None:
            return None
        return decision.reason_text

    @db_transaction
    def apply_draft_update(
        self,
        application_id: uuid.UUID,
        changes: dict,
        *,
        expected_version: int,
    ) -> KycApplication:
        application = db.session.get(KycApplication, application_id)
        if application is None:
            raise UnknownKycApplicationError(str(application_id))
        now = utcnow()
        result = db.session.execute(
            update(KycApplication)
            .where(KycApplication.application_id == application_id)
            .where(KycApplication.version == expected_version)
            .values(
                **changes,
                version=expected_version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            raise KycVersionConflictError(
                f"Application {application_id} is no longer at version "
                f"{expected_version}; reload it and save again"
            )
        db.session.add(
            KycApplicationHistory(
                application_id=application_id,
                status=application.status,
                version_after=expected_version + 1,
                changed_at=now,
            )
        )
        db.session.flush()
        db.session.expire_all()
        updated = db.session.get(KycApplication, application_id)
        if updated is None:
            raise UnknownKycApplicationError(str(application_id))
        return updated

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
        risk_assessment: RiskAssessment | None = None,
        tier_decision: TierDecision | None = None,
        review_interval_days: int | None = None,
        processing_consented_at: datetime | None = None,
    ) -> KycApplication:
        """Move an application to `to_status`, with everything the move writes.

        The caller (`KycController.transition`) decides the risk assessment,
        tier and review interval; this method lands them — the status change,
        the history rows, the decision row and the assessment audit — in one
        transaction, conditional on the version.
        """
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
        if risk_assessment is not None:
            changes["risk_score"] = risk_assessment.score
            changes["risk_rating"] = risk_assessment.rating
        if to_status is KycStatus.SUBMITTED and application.submitted_at is None:
            changes["submitted_at"] = now
        if processing_consented_at is not None:
            changes["processing_consented_at"] = processing_consented_at
        if to_status is KycStatus.APPROVED:
            if tier_decision is None:
                tier_decision = TierDecision(KYC_TIER_VERIFIED, KYC_TIER_VERIFIED)
            changes["tier_granted"] = tier_decision.final_tier
            changes["next_review_at"] = now + timedelta(
                days=review_interval_days or REVIEW_INTERVAL_DAYS
            )

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

        if risk_assessment is not None:
            # A standing override survives the rescore, so the final rating is
            # still the reviewer's, and the reason is still theirs.
            override = application.risk_rating_override
            self._record_assessment(
                application_id,
                computed_risk_rating=risk_assessment.rating,
                final_risk_rating=override or risk_assessment.rating,
                risk_score=risk_assessment.score,
                reason=(
                    application.risk_rating_override_reason
                    if override is not None and override != risk_assessment.rating
                    else None
                ),
                actor_user_id=actor_user_id,
                recorded_at=now,
                matched_signals=[
                    (match.signal, match.score_effect)
                    for match in risk_assessment.matched_signals
                ],
            )

        if to_status is KycStatus.APPROVED:
            self._record_assessment(
                application_id,
                computed_tier=tier_decision.computed_tier,
                final_tier=tier_decision.final_tier,
                reason=(
                    tier_decision.reason
                    if tier_decision.final_tier != tier_decision.computed_tier
                    else None
                ),
                actor_user_id=actor_user_id,
                recorded_at=now,
            )

        db.session.refresh(application)
        return application

    @db_transaction
    def apply_risk_override(
        self,
        application_id: uuid.UUID,
        rating: str,
        *,
        reason: str,
        expected_version: int,
        actor_user_id: uuid.UUID,
    ) -> KycApplication:
        """Record a reviewer's rating alongside the computed one.

        The computed `risk_score` and `risk_rating` are left exactly as scored,
        so both values survive; the override lands in its own columns, bumps
        the version like any other change a second reviewer must not miss, and
        is audited with computed, final and reason.
        """
        application = db.session.get(KycApplication, application_id)
        if application is None:
            raise UnknownKycApplicationError(str(application_id))

        status = KycStatus(application.status)
        if status not in RISK_OVERRIDABLE_STATUSES:
            raise KycRiskOverrideNotAllowedError(
                f"Application {application_id} is {status.value}; a risk rating "
                "can only be overridden while the application awaits a decision"
            )

        now = utcnow()
        result = db.session.execute(
            update(KycApplication)
            .where(KycApplication.application_id == application_id)
            .where(KycApplication.version == expected_version)
            .values(
                risk_rating_override=rating,
                risk_rating_override_reason=reason,
                risk_rating_overridden_by_user_id=actor_user_id,
                risk_rating_overridden_at=now,
                version=expected_version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            raise KycVersionConflictError(
                f"Application {application_id} is no longer at version "
                f"{expected_version}; reload it and decide again"
            )

        db.session.add(
            KycApplicationHistory(
                application_id=application_id,
                status=status.value,
                version_after=expected_version + 1,
                risk_rating=rating,
                reason_text=reason,
                changed_by_user_id=actor_user_id,
                changed_at=now,
            )
        )
        self._record_assessment(
            application_id,
            computed_risk_rating=application.risk_rating,
            final_risk_rating=rating,
            risk_score=application.risk_score,
            reason=reason,
            actor_user_id=actor_user_id,
            recorded_at=now,
        )

        db.session.refresh(application)
        return application

    def _record_assessment(
        self,
        application_id: uuid.UUID,
        *,
        actor_user_id: uuid.UUID | None,
        recorded_at,
        reason: str | None,
        computed_risk_rating: str | None = None,
        final_risk_rating: str | None = None,
        risk_score: int | None = None,
        computed_tier: int | None = None,
        final_tier: int | None = None,
        matched_signals: list[tuple[str, int]] | None = None,
    ) -> None:
        entry = KycAssessmentAudit(
            application_id=application_id,
            computed_risk_rating=computed_risk_rating,
            final_risk_rating=final_risk_rating,
            risk_score=risk_score,
            computed_tier=computed_tier,
            final_tier=final_tier,
            reason=reason,
            actor_user_id=actor_user_id,
            recorded_at=recorded_at,
        )
        db.session.add(entry)
        db.session.flush()
        for signal, score_effect in matched_signals or ():
            db.session.add(
                KycAssessmentAuditSignal(
                    audit_id=entry.audit_id,
                    signal=signal,
                    score_effect=score_effect,
                )
            )
