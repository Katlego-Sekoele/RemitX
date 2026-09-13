"""Applicant-facing KYC application endpoints.

HTTP only. The draft, `next_step`, and submit completeness live in
`KycOnboardingController`. The applicant sees their own unmasked values —
they typed them — which is why this uses `KycApplicationReadPII` without the
staff `kyc:application:read_pii` gate.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, status

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.kyc_onboarding_controller import (
    KycOnboardingController,
    KycOnboardingView,
)
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.kyc import KycApplicationReadPII, KycStandingRead
from remitx_api.models.schemas.kyc_onboarding import (
    KycApplicationPatch,
    KycCountryRead,
    KycIdentitySchemeRead,
    KycOnboardingRead,
    KycOnboardingStepRead,
    KycReferenceRead,
    KycStartRequest,
    KycSubmitRequest,
)
from remitx_api.routes.routers import create_customer_router

router: APIRouter = create_customer_router(prefix="/kyc", tags=["kyc"])
controller = KycOnboardingController()


def _read(view: KycOnboardingView) -> KycOnboardingRead:
    return KycOnboardingRead(
        standing=KycStandingRead.model_validate(view.standing),
        application=(
            None
            if view.application is None
            else KycApplicationReadPII.model_validate(view.application)
        ),
        next_step=view.next_step,
        rejection_reason=view.rejection_reason,
        stored_document_types=list(view.stored_document_types),
        pep_relationships=view.pep_relationships,
        steps=[
            KycOnboardingStepRead(
                step=step.step,
                position=step.position,
                role=step.role,
                description=step.description,
            )
            for step in view.catalogue.steps
        ],
    )


@router.get("/reference", response_model=KycReferenceRead)
def get_reference():
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


@router.get("/application", response_model=KycOnboardingRead)
def get_application(user: User = Depends(get_current_user)):
    return _read(controller.get(user.id))


@router.post(
    "/application",
    response_model=KycOnboardingRead,
    status_code=status.HTTP_200_OK,
)
def start_application(
    payload: Annotated[KycStartRequest | None, Body()] = None,
    user: User = Depends(get_current_user),
):
    residential_country = None if payload is None else payload.residential_country
    return _read(controller.start(user.id, residential_country=residential_country))


@router.patch("/application", response_model=KycOnboardingRead)
def patch_application(
    payload: KycApplicationPatch,
    user: User = Depends(get_current_user),
):
    fields = payload.model_dump(exclude_unset=True)
    expected_version = fields.pop("expected_version")
    return _read(controller.patch(user.id, fields, expected_version=expected_version))


@router.post("/submit", response_model=KycOnboardingRead)
def submit_application(
    payload: KycSubmitRequest,
    user: User = Depends(get_current_user),
):
    return _read(
        controller.submit(
            user.id,
            expected_version=payload.expected_version,
            consent=payload.consent,
        )
    )
