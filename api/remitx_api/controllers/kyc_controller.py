"""The one place a KYC application's status, risk rating or tier changes.

Every status change in the system goes through `KycController.transition`.
Assigning `application.status` anywhere else is a bug: it skips the legality
check, the audit rows, and the version bump that stops one reviewer
overwriting another. The same goes for the risk rating — scored inside
`transition` on submission, overridden only through `override_risk_rating`.

Database access lives in the repositories and the rules in
services/kyc_risk_rules.py; this controller holds orchestration and the
refusals that depend on the application in hand.
"""

import uuid
from datetime import datetime

from remitx_api.db.transaction import db_transaction
from remitx_api.errors.kyc import (
    IllegalKycTransitionError,
    KycSelfReviewError,
    KycSeniorApprovalRequiredError,
    KycTierNotGrantableError,
    UnknownKycApplicationError,
    UnknownKycReasonCodeError,
)
from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_lifecycle import (
    DECISION_STATUSES,
    KYC_TIER_VERIFIED,
    TIPPING_OFF_REASON_CODES,
    KycReasonCode,
    KycStatus,
    applicant_message_for,
)
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.repositories.kyc_application_repository import (
    QUEUE_STATUSES,
    KycApplicationRepository,
    KycStanding,
    TierDecision,
)
from remitx_api.repositories.kyc_risk_rule_repository import (
    KycRiskRuleRepository,
    band_from_record,
)
from remitx_api.repositories.kyc_status_progression_repository import (
    KycApplicationStatusProgressionRepository,
)
from remitx_api.repositories.permission_repository import PermissionRepository
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services.audit_service import record_audit
from remitx_api.services.kyc_risk_rules import (
    RiskAssessment,
    RiskBand,
    RiskFacts,
    assess_risk,
    require_risk_declarations,
)

# Approving and rejecting are the decisions a PEP declaration or a
# senior-approval rating reserves for `kyc:application:decide`. Claiming an
# application and asking for more information stay with whoever may do them.
OUTCOME_STATUSES = frozenset({KycStatus.APPROVED, KycStatus.REJECTED})


class KycController:
    def __init__(self) -> None:
        self._applications = KycApplicationRepository()
        self._progressions = KycApplicationStatusProgressionRepository()
        self._rules = KycRiskRuleRepository()
        self._permissions = PermissionRepository()
        self._users = UserRepository()

    def get_standing(self, user_id: uuid.UUID) -> KycStanding:
        return self._applications.get_standing(user_id)

    def start_application(self, user_id: uuid.UUID) -> KycApplication:
        self._users.require_by_id(user_id)
        return self._applications.create_open_application(user_id)

    def list_queue(
        self,
        *,
        statuses: list[KycStatus] | None = None,
        risk_rating: str | None = None,
        min_age_days: int | None = None,
    ) -> list[KycApplication]:
        if risk_rating is not None:
            # Refuse a rating that is not a row, rather than answer an empty
            # queue that looks like "nothing is high risk".
            self._rules.require_rating(risk_rating)
        applications = self._applications.list_queue(
            statuses=statuses or QUEUE_STATUSES,
            risk_rating=risk_rating,
            min_age_days=min_age_days,
        )
        self._attach_reviewers(applications)
        return applications

    def queue_count(self) -> int:
        return self._applications.count_queue()

    def get_application(self, application_id: uuid.UUID) -> KycApplication:
        application = self._require(application_id)
        self._attach_reviewers([application])
        return application

    @db_transaction
    def reveal_pii(
        self, application_id: uuid.UUID, *, actor_user_id: uuid.UUID
    ) -> KycApplication:
        """The unmasked record, and the audit entry that records looking."""
        application = self._require(application_id)
        record_audit(
            actor_user_id=actor_user_id,
            action=AuditAction.KYC_PII_VIEWED,
            subject_type=AuditSubject.KYC_APPLICATION,
            subject_id=application.application_id,
            after={"status": application.status},
        )
        self._attach_reviewers([application])
        return application

    def start_review(
        self,
        application_id: uuid.UUID,
        *,
        expected_version: int,
        actor_user_id: uuid.UUID,
    ) -> KycApplication:
        application = self._require(application_id)
        self._forbid_self_review(application, actor_user_id)
        if application.status == KycStatus.UNDER_REVIEW.value:
            self._attach_reviewers([application])
            return application
        return self.transition(
            application_id,
            KycStatus.UNDER_REVIEW,
            expected_version=expected_version,
            actor_user_id=actor_user_id,
        )

    def list_reason_codes(self):
        return [
            {
                "reason_code": row.reason_code,
                "description": row.description,
                "applicant_message": applicant_message_for(row.reason_code)
                or row.description,
                "visible_to_applicant": row.reason_code
                not in {code.value for code in TIPPING_OFF_REASON_CODES},
            }
            for row in self._applications.list_reason_codes()
        ]

    def transition(
        self,
        application_id: uuid.UUID,
        to_status: KycStatus | str,
        *,
        expected_version: int,
        actor_user_id: uuid.UUID | None = None,
        reason_code: KycReasonCode | str | None = None,
        reason_text: str | None = None,
        tier_granted: int | None = None,
        processing_consented_at: datetime | None = None,
    ) -> KycApplication:
        """Move an application to `to_status`.

        On submission the application is scored against the rule set as the
        database holds it now, and refused if a declaration it made leaves a
        mandatory field empty. On approval or rejection, a PEP declaration or a
        senior-approval rating requires the actor to hold
        `kyc:application:decide`. On approval, the tier is checked against
        `kyc_tiers` and the rating, and the next review is scheduled from the
        rating's interval.
        """
        to_status = self._as_status(to_status)
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise UnknownKycApplicationError(str(application_id))
        # Legality first, so an illegal move is reported as one rather than as
        # whatever the checks below would have made of it.
        self._require_legal(application, to_status)
        if to_status in DECISION_STATUSES:
            self._forbid_self_review(application, actor_user_id)
        if reason_code is not None:
            self._require_reason_code(reason_code)

        risk_assessment: RiskAssessment | None = None
        tier_decision: TierDecision | None = None
        band = self._band_for(application)

        if to_status is KycStatus.SUBMITTED:
            require_risk_declarations(application)
            risk_assessment = assess_risk(
                RiskFacts.from_application(application),
                self._rules.load_rule_set(),
            )

        if to_status in OUTCOME_STATUSES and self._requires_senior_approval(
            application, band
        ):
            self._require_permission(
                actor_user_id,
                PermissionCode.KYC_APPLICATION_DECIDE,
                KycSeniorApprovalRequiredError(
                    "This application carries a PEP declaration or a risk rating "
                    "that requires a compliance officer's decision "
                    f"({PermissionCode.KYC_APPLICATION_DECIDE.value})"
                ),
            )

        if to_status is KycStatus.APPROVED:
            tier_decision = self._decide_tier(
                application,
                band,
                requested_tier=tier_granted,
                actor_user_id=actor_user_id,
                reason=reason_text,
            )

        updated = self._applications.apply_transition(
            application_id,
            to_status,
            expected_version=expected_version,
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            reason_text=reason_text,
            risk_assessment=risk_assessment,
            tier_decision=tier_decision,
            review_interval_days=None if band is None else band.review_interval_days,
            processing_consented_at=processing_consented_at,
        )
        self._attach_reviewers([updated])
        return updated

    def override_risk_rating(
        self,
        application_id: uuid.UUID,
        rating: str,
        *,
        reason: str,
        expected_version: int,
        actor_user_id: uuid.UUID,
    ) -> KycApplication:
        """A reviewer's rating, stored beside the computed one with a reason.

        The route gates this on `kyc:risk:write`. The reason's presence is
        checked by the request schema and again by the database.
        """
        self._rules.require_rating(rating)
        return self._applications.apply_risk_override(
            application_id,
            rating,
            reason=reason.strip(),
            expected_version=expected_version,
            actor_user_id=actor_user_id,
        )

    def list_assessment_audit(self, application_id: uuid.UUID):
        self._require(application_id)
        return self._applications.list_assessment_audit(application_id)

    # --- refusals that depend on the application ------------------------------

    def _require(self, application_id: uuid.UUID) -> KycApplication:
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise UnknownKycApplicationError(str(application_id))
        return application

    def _attach_reviewers(self, applications: list[KycApplication]) -> None:
        reviewers = self._applications.latest_reviewers(
            [application.application_id for application in applications]
        )
        for application in applications:
            application.reviewer_user_id = reviewers.get(application.application_id)

    @staticmethod
    def _forbid_self_review(
        application: KycApplication, actor_user_id: uuid.UUID | None
    ) -> None:
        if actor_user_id is not None and actor_user_id == application.user_id:
            raise KycSelfReviewError(
                "A reviewer cannot decide on their own application"
            )

    def _require_reason_code(self, reason_code: KycReasonCode | str) -> None:
        value = (
            reason_code.value if isinstance(reason_code, KycReasonCode) else reason_code
        )
        codes = {row.reason_code for row in self._applications.list_reason_codes()}
        if value not in codes:
            raise UnknownKycReasonCodeError(value)

    def _require_legal(self, application: KycApplication, to_status: KycStatus):
        if not self._progressions.is_allowed(application.status, to_status.value):
            raise IllegalKycTransitionError(
                f"Cannot move application {application.application_id} from "
                f"{application.status} to {to_status.value}"
            )

    def _band_for(self, application: KycApplication) -> RiskBand | None:
        rating = application.effective_risk_rating
        if rating is None:
            return None
        return band_from_record(self._rules.require_rating(rating))

    @staticmethod
    def _requires_senior_approval(
        application: KycApplication, band: RiskBand | None
    ) -> bool:
        # The PEP rule does not wait for a rating: a PEP application whose
        # signal was switched off, or reweighted below `high`, still needs an
        # officer. FICA asks for senior management approval of the relationship
        # itself, not of a score.
        return application.declares_pep or (
            band is not None and band.requires_senior_approval
        )

    def _require_permission(
        self,
        actor_user_id: uuid.UUID | None,
        permission: PermissionCode,
        refusal: Exception,
    ) -> None:
        if actor_user_id is None:
            raise refusal
        if permission not in self._permissions.get_effective_permissions(actor_user_id):
            raise refusal

    def _decide_tier(
        self,
        application: KycApplication,
        band: RiskBand | None,
        *,
        requested_tier: int | None,
        actor_user_id: uuid.UUID | None,
        reason: str | None,
    ) -> TierDecision:
        computed = KYC_TIER_VERIFIED
        final = computed if requested_tier is None else requested_tier

        tier = self._rules.get_tier(final)
        if tier is None or final < KYC_TIER_VERIFIED:
            raise KycTierNotGrantableError(
                f"Tier {final} cannot be granted on approval; approval grants a "
                f"tier of at least {KYC_TIER_VERIFIED} defined in kyc_tiers"
            )
        if band is not None and final > band.max_tier:
            raise KycTierNotGrantableError(
                f"A {band.rating} risk rating allows tier {band.max_tier} at most"
            )
        if tier.requires_source_of_wealth and not (
            application.source_of_wealth and application.source_of_wealth.strip()
        ):
            raise KycTierNotGrantableError(
                f"Tier {final} ({tier.name}) requires a declared source of wealth"
            )

        if final != computed:
            self._require_permission(
                actor_user_id,
                PermissionCode.KYC_RISK_WRITE,
                KycSeniorApprovalRequiredError(
                    f"Granting tier {final} instead of tier {computed} requires "
                    f"{PermissionCode.KYC_RISK_WRITE.value}"
                ),
            )
            if not (reason and reason.strip()):
                raise KycTierNotGrantableError(
                    f"Granting tier {final} instead of tier {computed} requires a "
                    "reason"
                )

        return TierDecision(
            computed_tier=computed,
            final_tier=final,
            reason=None if reason is None else reason.strip(),
        )

    @staticmethod
    def _as_status(value: KycStatus | str) -> KycStatus:
        try:
            return KycStatus(value)
        except ValueError as exc:
            raise IllegalKycTransitionError(f"Unknown KYC status: {value!r}") from exc
