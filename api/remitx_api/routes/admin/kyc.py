"""The KYC reviewer queue and the risk rating that orders it.

The router's baseline is `kyc:application:read`, and everything it returns is
masked — `KycApplicationRead`, never the ORM row, never the PII view. Overriding
a rating escalates to `kyc:risk:write`.

Approve, reject and request-info are the review ticket's (#20), and go through
`KycController.transition`, which is where the PEP and senior-approval rules
are enforced — they depend on the application, so no route gate could.

HTTP only: refusals are raised by the controller from ``remitx_api.errors`` and
turned into responses by the handler in app.py.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from remitx_api.auth.dependencies import get_current_user
from remitx_api.auth.permissions import RequirePermission
from remitx_api.controllers.kyc_controller import KycController
from remitx_api.models.orm.kyc_lifecycle import KycStatus
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.kyc import (
    KycApplicationRead,
    KycAssessmentAuditRead,
    KycMatchedSignalRead,
    KycRiskOverrideRequest,
    KycRiskRulesRead,
)
from remitx_api.repositories.kyc_risk_rule_repository import KycRiskRuleRepository
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.KYC_APPLICATION_READ,
    prefix="/admin/kyc",
    tags=["admin"],
)
controller = KycController()
rules = KycRiskRuleRepository()


@router.get("/applications", response_model=list[KycApplicationRead])
def list_applications(
    risk_rating: Annotated[
        str | None,
        Query(description="Only applications whose effective rating is this."),
    ] = None,
    status: Annotated[
        list[KycStatus] | None,
        Query(description="Statuses to include. Defaults to submitted, under_review."),
    ] = None,
):
    """The reviewer queue: highest risk first, then oldest submission first."""
    applications = controller.list_queue(statuses=status, risk_rating=risk_rating)
    return [KycApplicationRead.model_validate(row) for row in applications]


@router.get("/risk-rules", response_model=KycRiskRulesRead)
def get_risk_rules():
    """Signals, rating bands, tiers and PEP relationships, as scored against."""
    return KycRiskRulesRead(
        signals=rules.list_signals(),
        ratings=rules.list_ratings(),
        tiers=rules.list_tiers(),
        pep_relationships=rules.list_pep_relationships(),
    )


@router.get(
    "/applications/{application_id}/assessment-audit",
    response_model=list[KycAssessmentAuditRead],
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
)
def override_risk_rating(
    application_id: uuid.UUID,
    payload: KycRiskOverrideRequest,
    # Not a gate — the dependency above is. The override records who made it.
    actor: User = Depends(get_current_user),
):
    """Set a reviewer's rating beside the computed one. Both survive."""
    application = controller.override_risk_rating(
        application_id,
        payload.rating,
        reason=payload.reason,
        expected_version=payload.expected_version,
        actor_user_id=actor.id,
    )
    return KycApplicationRead.model_validate(application)
