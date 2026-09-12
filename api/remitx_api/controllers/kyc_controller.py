"""The one place a KYC application's status changes.

Every status change in the system goes through `KycController.transition`.
Assigning `application.status` anywhere else is a bug: it skips the legality
check, the audit rows, and the version bump that stops one reviewer
overwriting another.

Database access lives in `KycApplicationRepository`; this controller holds
orchestration and validation only.
"""

import uuid

from remitx_api.errors.kyc import (
    IllegalKycTransitionError,
)
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_lifecycle import (
    KycReasonCode,
    KycRiskRating,
    KycStatus,
)
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
    KycStanding,
)
from remitx_api.repositories.user_repository import UserRepository


class KycController:
    def __init__(self) -> None:
        self._applications = KycApplicationRepository()
        self._users = UserRepository()

    def get_standing(self, user_id: uuid.UUID) -> KycStanding:
        return self._applications.get_standing(user_id)

    def start_application(self, user_id: uuid.UUID) -> KycApplication:
        self._users.require_by_id(user_id)
        return self._applications.create_open_application(user_id)

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
        to_status = self._as_status(to_status)
        return self._applications.apply_transition(
            application_id,
            to_status,
            expected_version=expected_version,
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            reason_text=reason_text,
            risk_rating=risk_rating,
            tier_granted=tier_granted,
        )

    @staticmethod
    def _as_status(value: KycStatus | str) -> KycStatus:
        try:
            return KycStatus(value)
        except ValueError as exc:
            raise IllegalKycTransitionError(f"Unknown KYC status: {value!r}") from exc
