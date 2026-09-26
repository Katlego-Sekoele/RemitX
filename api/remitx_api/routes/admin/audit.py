"""Privileged-action audit log — read-only listing for compliance staff."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query
from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.audit_controller import (
    DEFAULT_AUDIT_PAGE_SIZE,
    MAX_AUDIT_PAGE_SIZE,
    AuditController,
)
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.audit import AuditLogRead
from remitx_api.openapi import Tag
from remitx_api.routes.routers import create_admin_router

router = create_admin_router(
    permission=PermissionCode.AUDIT_READ,
    prefix="/admin/audit",
    tags=[Tag.ADMIN_AUDIT],
)
controller = AuditController()


@router.get(
    "",
    response_model=list[AuditLogRead],
    summary="List privileged actions and sensitive reads",
)
def list_audit_log(
    actor_user_id: Annotated[
        uuid.UUID | None,
        Query(description="Only entries written by this staff member."),
    ] = None,
    action: Annotated[
        str | None,
        Query(description="Exact action string, e.g. ``kyc.pii.viewed``."),
    ] = None,
    subject_type: Annotated[
        str | None,
        Query(description="Subject kind, e.g. ``kyc_application``."),
    ] = None,
    subject_id: Annotated[
        uuid.UUID | None,
        Query(description="Id of the record that was acted on or read."),
    ] = None,
    created_after: Annotated[
        datetime | None,
        Query(description="Inclusive lower bound on ``created_at`` (UTC)."),
    ] = None,
    created_before: Annotated[
        datetime | None,
        Query(description="Exclusive upper bound on ``created_at`` (UTC)."),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_AUDIT_PAGE_SIZE,
            description="Page size. A full page means there may be more.",
        ),
    ] = DEFAULT_AUDIT_PAGE_SIZE,
    before: Annotated[
        datetime | None,
        Query(
            description=(
                "Only entries created before this instant. Pass the last row's "
                "`created_at` to fetch the next page."
            ),
        ),
    ] = None,
    operator: User = Depends(get_current_user),
):
    """Reverse-chronological audit trail. Needs ``audit:read``. Opening a page
    writes a ``audit.log.viewed`` entry describing the filters used."""
    return controller.list_audit(
        actor_user_id=operator.id,
        actor_user_id_filter=actor_user_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        before=before,
    )
