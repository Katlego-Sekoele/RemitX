"""Applicant-facing KYC application endpoints.

HTTP only. The draft, `next_step`, and submit completeness live in
`KycOnboardingController`. The applicant sees their own unmasked values —
they typed them — through `KycApplicantApplicationRead`, which carries none of
the staff assessment fields.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.caching import cache, key_from_args
from remitx_api.caching.namespaces import Namespace
from remitx_api.controllers.kyc_onboarding_controller import (
    KycApplicationDetailView,
    KycOnboardingController,
    KycOnboardingView,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.kyc import KycStandingRead
from remitx_api.models.schemas.kyc_onboarding import (
    KycApplicantApplicationRead,
    KycApplicationDetailRead,
    KycApplicationPatch,
    KycApplicationSummaryRead,
    KycCountryRead,
    KycIdentitySchemeRead,
    KycOnboardingRead,
    KycOnboardingStepRead,
    KycReferenceRead,
    KycStartRequest,
    KycStatusEventRead,
    KycSubmitRequest,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router

router: APIRouter = create_customer_router(prefix="/kyc", tags=[Tag.KYC_ONBOARDING])
controller = KycOnboardingController()

# Only a migration changes the reference data, and the client already keeps
# it for the whole session; after a deploy that does, the old copy is served
# for up to this long.
REFERENCE_CACHE_SECONDS = 3600


def _steps(view: KycOnboardingView | KycApplicationDetailView):
    return [
        KycOnboardingStepRead(
            step=step.step,
            position=step.position,
            role=step.role,
            description=step.description,
        )
        for step in view.catalogue.steps
    ]


def _read(view: KycOnboardingView) -> KycOnboardingRead:
    return KycOnboardingRead(
        standing=KycStandingRead.model_validate(view.standing),
        application=(
            None
            if view.application is None
            else KycApplicantApplicationRead.model_validate(view.application)
        ),
        next_step=view.next_step,
        stored_document_types=list(view.stored_document_types),
        pep_relationships=view.pep_relationships,
        steps=_steps(view),
    )


def _detail(view: KycApplicationDetailView) -> KycApplicationDetailRead:
    return KycApplicationDetailRead(
        application=KycApplicantApplicationRead.model_validate(view.application),
        editable=view.editable,
        applicant_message=view.applicant_message,
        timeline=[KycStatusEventRead.model_validate(row) for row in view.timeline],
        next_step=view.next_step,
        stored_document_types=list(view.stored_document_types),
        pep_relationships=view.pep_relationships,
        steps=_steps(view),
    )


@router.get(
    "/reference",
    response_model=KycReferenceRead,
    summary="Get onboarding reference data",
)
@cache(
    expire=REFERENCE_CACHE_SECONDS,
    namespace=Namespace.KYC_REFERENCE,
    key_builder=key_from_args(),
)
def get_reference():
    """Countries, and the identity schemes each one accepts."""
    # Authenticated by the router; the reference data is the same for everyone.
    catalogue = controller.reference()
    return KycReferenceRead(
        countries=[
            KycCountryRead(
                code=country.code,
                name=country.name,
                operates_in=country.operates_in,
            )
            for country in catalogue.countries
        ],
        identity_schemes=[
            KycIdentitySchemeRead(
                scheme=scheme.scheme,
                country=scheme.country,
                id_type=scheme.id_type,
                label=scheme.label,
                requires_expiry=scheme.requires_expiry,
                input_mode=scheme.input_mode,
                number_hint=scheme.number_hint,
                document_hint=scheme.document_hint,
            )
            for scheme in catalogue.schemes
        ],
    )


@router.get(
    "/application",
    response_model=KycOnboardingRead,
    summary="Get the caller's KYC standing",
)
def get_application(user: User = Depends(get_current_user)):
    """Standing, the application the caller is on now if any, and its next
    step. The whole history is `GET /kyc/applications`."""
    return _read(controller.get(user.id))


@router.get(
    "/applications",
    response_model=list[KycApplicationSummaryRead],
    summary="List the caller's KYC applications",
)
def list_my_applications(user: User = Depends(get_current_user)):
    """Newest first."""
    return [
        KycApplicationSummaryRead(
            application_id=summary.application.application_id,
            status=summary.application.effective_status,
            created_at=summary.application.created_at,
            submitted_at=summary.application.submitted_at,
            decided_at=summary.decided_at,
            tier_granted=summary.application.tier_granted,
            next_review_at=summary.application.next_review_at,
            editable=summary.editable,
        )
        for summary in controller.list_for_user(user.id)
    ]


@router.post(
    "/applications",
    response_model=KycApplicationDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Start or resume a KYC application",
    responses=error_responses(400, 409),
)
def start_application(
    payload: Annotated[KycStartRequest | None, Body()] = None,
    user: User = Depends(get_current_user),
):
    """Returns the open application if there is one. Otherwise opens a new one,
    but only while the caller has no approval or it has expired — 409 while an
    approval is in force. A residence outside the countries RemitX operates in
    is refused before any application exists."""
    residential_country = None if payload is None else payload.residential_country
    return _detail(controller.start(user.id, residential_country=residential_country))


@router.get(
    "/applications/{application_id}",
    response_model=KycApplicationDetailRead,
    summary="Get one of the caller's KYC applications",
    responses=error_responses(404),
)
def get_my_application(
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """The caller's own values, the applicant-safe reviewer message, and the
    status timeline. Another user's application is a 404."""
    return _detail(controller.detail(user.id, application_id))


@router.patch(
    "/applications/{application_id}",
    response_model=KycApplicationDetailRead,
    summary="Save fields on a KYC draft",
    responses=error_responses(400, 404, 409),
)
def patch_application(
    application_id: uuid.UUID,
    payload: KycApplicationPatch,
    user: User = Depends(get_current_user),
):
    """Only the fields sent are changed. ``expected_version`` must match the
    draft's, so a stale tab gets a 409 instead of overwriting. Refused once the
    application is no longer editable."""
    fields = payload.model_dump(exclude_unset=True)
    expected_version = fields.pop("expected_version")
    return _detail(
        controller.patch(
            user.id, application_id, fields, expected_version=expected_version
        )
    )


@router.post(
    "/applications/{application_id}/submit",
    response_model=KycApplicationDetailRead,
    summary="Submit a KYC application for review",
    responses=error_responses(400, 404, 409),
)
def submit_application(
    application_id: uuid.UUID,
    payload: KycSubmitRequest,
    user: User = Depends(get_current_user),
):
    """Scores the application and queues it for a reviewer. Refused while any
    required field or document is missing, or without processing consent."""
    return _detail(
        controller.submit(
            user.id,
            application_id,
            expected_version=payload.expected_version,
            consent=payload.consent,
        )
    )
