"""The KYC reviewer queue and the decisions taken from it.

The router's baseline is `kyc:application:read`, and everything it returns is
masked — `KycApplicationRead`, never the ORM row, never the PII view.
Revealing PII, claiming an application, requesting more information, and
deciding each escalate to their own permission.

Approve and reject go through `KycController.transition`, which is where the
PEP and senior-approval rules are enforced — they depend on the application,
so no route gate could.

HTTP only: refusals are raised by the controller from ``remitx_api.errors`` and
turned into responses by the handler in app.py.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.caching import invalidate_cache
from remitx_api.caching.namespaces import Namespace
from remitx_api.controllers.kyc_controller import KycController
from remitx_api.models.orm.kyc_lifecycle import KycReasonCode, KycStatus
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.kyc import (
    KycApplicationRead,
    KycApplicationReadPII,
    KycApproveRequest,
    KycAssessmentAuditRead,
    KycMatchedSignalRead,
    KycQueueCountRead,
    KycReasonCodeRead,
    KycRejectRequest,
    KycRequestInfoRequest,
    KycReviewRequest,
    KycRiskOverrideRequest,
    KycRiskRulesRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.repositories.kyc_risk_rule_repository import KycRiskRuleRepository
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.KYC_APPLICATION_READ,
    prefix="/admin/kyc",
    tags=[Tag.ADMIN_KYC_APPLICATIONS],
)
controller = KycController()
rules = KycRiskRuleRepository()


@router.get(
    "/applications",
    response_model=list[KycApplicationRead],
    summary="List the KYC reviewer queue",
)
def list_applications(
    risk_rating: Annotated[
        str | None,
        Query(description="Only applications whose effective rating is this."),
    ] = None,
    status: Annotated[
        list[KycStatus] | None,
        Query(description="Statuses to include. Defaults to submitted, under_review."),
    ] = None,
    min_age_days: Annotated[
        int | None,
        Query(
            ge=0,
            description="Only applications submitted at least this many days ago.",
        ),
    ] = None,
):
    """The reviewer queue: highest risk first, then oldest submission first."""
    applications = controller.list_queue(
        statuses=status, risk_rating=risk_rating, min_age_days=min_age_days
    )
    return [KycApplicationRead.model_validate(row) for row in applications]


@router.get(
    "/queue-count",
    response_model=KycQueueCountRead,
    summary="Count applications waiting on a reviewer",
)
def get_queue_count():
    """Submitted plus under review — the badge on the admin nav."""
    return KycQueueCountRead(count=controller.queue_count())


@router.get(
    "/reason-codes",
    response_model=list[KycReasonCodeRead],
    summary="List KYC reviewer reason codes",
)
def list_reason_codes():
    """The controlled list a reject or request-info must name."""
    return [
        KycReasonCodeRead.model_validate(row) for row in controller.list_reason_codes()
    ]


@router.get(
    "/risk-rules",
    response_model=KycRiskRulesRead,
    summary="Get the KYC risk rule set",
)
def get_risk_rules():
    """Signals, rating bands, tiers and PEP relationships, as scored against."""
    return KycRiskRulesRead(
        signals=rules.list_signals(),
        ratings=rules.list_ratings(),
        tiers=rules.list_tiers(),
        pep_relationships=rules.list_pep_relationships(),
    )


@router.get(
    "/applications/{application_id}",
    response_model=KycApplicationRead,
    summary="Get one KYC application",
    responses=error_responses(404),
)
def get_review_application(application_id: uuid.UUID):
    """Masked. Revealing PII is a separate, audited action."""
    return KycApplicationRead.model_validate(controller.get_application(application_id))


@router.post(
    "/applications/{application_id}/reveal-pii",
    response_model=KycApplicationReadPII,
    dependencies=[Depends(RequirePermission(PermissionCode.KYC_APPLICATION_READ_PII))],
    summary="Reveal an application's unmasked identity fields",
    responses=error_responses(403, 404),
)
def reveal_application_pii(
    application_id: uuid.UUID,
    actor: User = Depends(get_current_user),
):
    """Writes a ``kyc.pii.viewed`` audit entry. Needs ``kyc:application:read_pii``."""
    return KycApplicationReadPII.model_validate(
        controller.reveal_pii(application_id, actor_user_id=actor.id)
    )


@router.post(
    "/applications/{application_id}/start-review",
    response_model=KycApplicationRead,
    dependencies=[
        Depends(RequirePermission(PermissionCode.KYC_APPLICATION_REQUEST_INFO))
    ],
    summary="Claim a submitted application for review",
    responses=error_responses(403, 404, 409),
)
def start_application_review(
    application_id: uuid.UUID,
    payload: KycReviewRequest,
    actor: User = Depends(get_current_user),
):
    """Moves ``submitted`` to ``under_review``. Already claimed stays as it is
    so a second reviewer sees who has it."""
    return KycApplicationRead.model_validate(
        controller.start_review(
            application_id,
            expected_version=payload.expected_version,
            actor_user_id=actor.id,
        )
    )


@router.post(
    "/applications/{application_id}/approve",
    response_model=KycApplicationRead,
    dependencies=[Depends(RequirePermission(PermissionCode.KYC_APPLICATION_DECIDE))],
    summary="Approve a KYC application",
    responses=error_responses(400, 403, 404, 409),
)
# Approval copies the verified name and country onto the applicant, which is
# what every sender who has added them sees in their beneficiary list.
@invalidate_cache(namespace=Namespace.BENEFICIARY_LIST)
def approve_application(
    application_id: uuid.UUID,
    payload: KycApproveRequest,
    actor: User = Depends(get_current_user),
):
    """Sets status, grants the tier, and writes the decision in one transaction.

    Needs ``kyc:application:decide``.
    """
    return KycApplicationRead.model_validate(
        controller.transition(
            application_id,
            KycStatus.APPROVED,
            expected_version=payload.expected_version,
            actor_user_id=actor.id,
            reason_code=payload.reason_code or KycReasonCode.IDENTITY_VERIFIED,
            reason_text=payload.reason_text,
            tier_granted=payload.tier_granted,
        )
    )


@router.post(
    "/applications/{application_id}/reject",
    response_model=KycApplicationRead,
    dependencies=[Depends(RequirePermission(PermissionCode.KYC_APPLICATION_DECIDE))],
    summary="Reject a KYC application",
    responses=error_responses(400, 403, 404, 409),
)
def reject_application(
    application_id: uuid.UUID,
    payload: KycRejectRequest,
    actor: User = Depends(get_current_user),
):
    """Needs a reason code. The internal note is never shown to the applicant."""
    return KycApplicationRead.model_validate(
        controller.transition(
            application_id,
            KycStatus.REJECTED,
            expected_version=payload.expected_version,
            actor_user_id=actor.id,
            reason_code=payload.reason_code,
            reason_text=payload.internal_note,
        )
    )


@router.post(
    "/applications/{application_id}/request-info",
    response_model=KycApplicationRead,
    dependencies=[
        Depends(RequirePermission(PermissionCode.KYC_APPLICATION_REQUEST_INFO))
    ],
    summary="Send a KYC application back for more information",
    responses=error_responses(400, 403, 404, 409),
)
def request_application_info(
    application_id: uuid.UUID,
    payload: KycRequestInfoRequest,
    actor: User = Depends(get_current_user),
):
    """``reason_text`` names the fields or documents the applicant must fix."""
    return KycApplicationRead.model_validate(
        controller.transition(
            application_id,
            KycStatus.MORE_INFO_REQUIRED,
            expected_version=payload.expected_version,
            actor_user_id=actor.id,
            reason_code=payload.reason_code,
            reason_text=payload.reason_text,
        )
    )


@router.get(
    "/applications/{application_id}/assessment-audit",
    response_model=list[KycAssessmentAuditRead],
    summary="List an application's risk assessment history",
    responses=error_responses(404),
)
def list_assessment_audit(application_id: uuid.UUID):
    """Every rating and tier change on one application, oldest first."""
    return [
        KycAssessmentAuditRead.model_validate(entry).model_copy(
            update={
                "matched_signals": [
                    KycMatchedSignalRead.model_validate(signal) for signal in signals
                ]
            }
        )
        for entry, signals in controller.list_assessment_audit(application_id)
    ]


@router.post(
    "/applications/{application_id}/risk-rating-override",
    response_model=KycApplicationRead,
    dependencies=[Depends(RequirePermission(PermissionCode.KYC_RISK_WRITE))],
    summary="Override an application's risk rating",
    responses=error_responses(400, 404, 409),
)
def override_risk_rating(
    application_id: uuid.UUID,
    payload: KycRiskOverrideRequest,
    # Not a gate — the dependency above is. The override records who made it.
    actor: User = Depends(get_current_user),
):
    """Set a reviewer's rating beside the computed one. Both survive.

    Needs ``kyc:risk:write``. ``expected_version`` must match the application's.
    """
    application = controller.override_risk_rating(
        application_id,
        payload.rating,
        reason=payload.reason,
        expected_version=payload.expected_version,
        actor_user_id=actor.id,
    )
    return KycApplicationRead.model_validate(application)
