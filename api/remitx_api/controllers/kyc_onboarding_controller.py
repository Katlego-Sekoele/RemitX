"""Applicant onboarding: draft, resume, and submit.

Status changes still go through `KycController.transition`. This controller
owns the draft: partial PATCH, the server-owned `next_step`, and the
completeness check submit uses — and the jurisdiction gate, which is enforced
at start, on every save, and again at submit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from remitx_api.clock import utcnow
from remitx_api.controllers.kyc_controller import KycController
from remitx_api.errors.kyc import (
    InvalidKycDraftError,
    KycApplicationNotEditableError,
    OpenApplicationExistsError,
)
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.kyc_pep_relationship import KycPepRelationshipRecord
from remitx_api.repositories.jurisdiction_repository import (
    JurisdictionCatalogue,
    JurisdictionRepository,
)
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
    KycStanding,
)
from remitx_api.repositories.kyc_document_repository import KycDocumentRepository
from remitx_api.repositories.kyc_onboarding_repository import (
    KycOnboardingRepository,
    OnboardingCatalogue,
)
from remitx_api.repositories.kyc_risk_rule_repository import KycRiskRuleRepository
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services.kyc_onboarding import (
    next_step,
    normalize_patch,
    normalize_residence,
    require_complete_for_submit,
    require_supported_residence,
    stored_types,
    validate_identification,
)


@dataclass(frozen=True)
class KycOnboardingView:
    standing: KycStanding
    application: KycApplication | None
    next_step: str
    rejection_reason: str | None
    stored_document_types: tuple[str, ...]
    pep_relationships: list[KycPepRelationshipRecord]
    catalogue: OnboardingCatalogue


class KycOnboardingController:
    def __init__(self) -> None:
        self._users = UserRepository()
        self._applications = KycApplicationRepository()
        self._documents = KycDocumentRepository()
        self._onboarding = KycOnboardingRepository()
        self._rules = KycRiskRuleRepository()
        self._jurisdictions = JurisdictionRepository()
        self._lifecycle = KycController()

    def get(self, user_id: uuid.UUID) -> KycOnboardingView:
        self._users.require_by_id(user_id)
        return self._view(user_id)

    def reference(self) -> JurisdictionCatalogue:
        return self._jurisdictions.load()

    def start(
        self,
        user_id: uuid.UUID,
        *,
        residential_country: str | None = None,
    ) -> KycOnboardingView:
        """Open (or resume) the draft. A residence, when given, is checked
        *before* anything is created, so someone we cannot serve never has an
        application at all."""
        self._users.require_by_id(user_id)
        residence = None
        if residential_country is not None:
            try:
                residence = normalize_residence(
                    residential_country, self._jurisdictions.load()
                )
            except ValueError as error:
                raise InvalidKycDraftError(str(error)) from error
        try:
            self._lifecycle.start_application(user_id)
        except OpenApplicationExistsError:
            # Welcome and resume both POST this; a draft already in flight is
            # the success case, not a conflict.
            pass
        if residence is not None:
            self._record_residence(user_id, residence)
        return self._view(user_id)

    def patch(
        self,
        user_id: uuid.UUID,
        fields: dict,
        *,
        expected_version: int,
    ) -> KycOnboardingView:
        self._users.require_by_id(user_id)
        application = self._require_editable(user_id)
        catalogue = self._onboarding.load()
        allowed = {
            requirement.name
            for requirement in catalogue.requirements
            if requirement.kind == "field"
        }
        unknown = set(fields) - allowed
        if unknown:
            raise InvalidKycDraftError("Unknown fields: " + ", ".join(sorted(unknown)))
        jurisdictions = self._jurisdictions.load()
        try:
            changes = normalize_patch(fields, jurisdictions)
            changes.update(
                self._identification_changes(application, changes, jurisdictions)
            )
        except ValueError as error:
            raise InvalidKycDraftError(str(error)) from error
        if changes:
            self._applications.apply_draft_update(
                application.application_id,
                changes,
                expected_version=expected_version,
            )
        return self._view(user_id)

    def submit(
        self,
        user_id: uuid.UUID,
        *,
        expected_version: int,
        consent: bool,
    ) -> KycOnboardingView:
        self._users.require_by_id(user_id)
        application = self._current_application(user_id)
        if application is None:
            raise KycApplicationNotEditableError(
                "There is no application to submit. Start onboarding first."
            )
        if application.status in {
            KycStatus.SUBMITTED.value,
            KycStatus.UNDER_REVIEW.value,
        }:
            return self._view(user_id)
        if not consent:
            raise InvalidKycDraftError(
                "Consent to process this information is required before submitting."
            )

        catalogue = self._onboarding.load()
        if application.status not in catalogue.editable_statuses:
            raise KycApplicationNotEditableError(
                "This application can no longer be submitted from here."
            )

        if application.status == KycStatus.MORE_INFO_REQUIRED.value:
            application = self._lifecycle.transition(
                application.application_id,
                KycStatus.IN_PROGRESS,
                expected_version=expected_version,
                actor_user_id=user_id,
            )
            expected_version = application.version

        types = stored_types(
            self._documents.list_for_application(
                application.application_id, stored_only=True
            )
        )
        jurisdictions = self._jurisdictions.load()
        # Again at submit: the draft may predate the gate, or the country may
        # have been switched off since it was saved.
        require_supported_residence(application.residential_country, jurisdictions)
        require_complete_for_submit(application, types, catalogue, jurisdictions)
        try:
            # And the identification, because a passport valid when saved can
            # have expired by the time the applicant presses submit.
            validate_identification(
                id_type=application.id_type,
                issuing_country=application.issuing_country,
                id_number=application.id_number,
                date_of_birth=application.date_of_birth,
                id_expiry_date=application.id_expiry_date,
                jurisdictions=jurisdictions,
            )
        except ValueError as error:
            raise InvalidKycDraftError(str(error)) from error
        self._lifecycle.transition(
            application.application_id,
            KycStatus.SUBMITTED,
            expected_version=expected_version,
            actor_user_id=user_id,
            processing_consented_at=utcnow(),
        )
        return self._view(user_id)

    def _identification_changes(
        self,
        application: KycApplication,
        changes: dict,
        jurisdictions: JurisdictionCatalogue,
    ) -> dict:
        """What the merged identification adds to a save: the number as its
        scheme normalises it, and a stale expiry cleared once the scheme no
        longer has one (a passport swapped for an SA ID)."""

        def merged(field: str):
            return changes.get(field, getattr(application, field))

        extra: dict = {}
        number = validate_identification(
            id_type=merged("id_type"),
            issuing_country=merged("issuing_country"),
            id_number=merged("id_number"),
            date_of_birth=merged("date_of_birth"),
            id_expiry_date=merged("id_expiry_date"),
            jurisdictions=jurisdictions,
        )
        if number != merged("id_number"):
            extra["id_number"] = number
        scheme = jurisdictions.resolve_scheme(
            merged("issuing_country"), merged("id_type")
        )
        if (
            scheme is not None
            and not scheme.requires_expiry
            and merged("id_expiry_date") is not None
        ):
            extra["id_expiry_date"] = None
        return extra

    def _record_residence(self, user_id: uuid.UUID, residence: str) -> None:
        application = self._applications.get_open_for_user(user_id)
        catalogue = self._onboarding.load()
        if (
            application is None
            or application.status not in catalogue.editable_statuses
            or application.residential_country == residence
        ):
            return
        self._applications.apply_draft_update(
            application.application_id,
            {"residential_country": residence},
            expected_version=application.version,
        )

    def _current_application(self, user_id: uuid.UUID) -> KycApplication | None:
        return self._applications.get_open_for_user(
            user_id
        ) or self._applications.get_latest_for_user(user_id)

    def _require_editable(self, user_id: uuid.UUID) -> KycApplication:
        application = self._applications.get_open_for_user(user_id)
        catalogue = self._onboarding.load()
        if application is None or application.status not in catalogue.editable_statuses:
            raise KycApplicationNotEditableError(
                "There is no draft to save. Start onboarding first."
            )
        return application

    def _view(self, user_id: uuid.UUID) -> KycOnboardingView:
        catalogue = self._onboarding.load()
        application = self._current_application(user_id)
        types: frozenset[str] = frozenset()
        if application is not None:
            types = stored_types(
                self._documents.list_for_application(
                    application.application_id, stored_only=True
                )
            )
        return KycOnboardingView(
            standing=self._applications.get_standing(user_id),
            application=application,
            next_step=next_step(
                application, types, catalogue, self._jurisdictions.load()
            ),
            rejection_reason=self._applications.latest_rejection_reason(user_id),
            stored_document_types=tuple(sorted(types)),
            pep_relationships=self._rules.list_pep_relationships(),
            catalogue=catalogue,
        )
