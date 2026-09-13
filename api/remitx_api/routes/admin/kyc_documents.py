"""Reviewer access to KYC evidence.

Gated on `kyc:document:read` at the router, which is what makes looking at
somebody's identity document a capability a role has to carry rather than a
side effect of being an admin. Every URL issued here is recorded in the audit
log before it is returned.
"""

import uuid

from fastapi import APIRouter, Depends
from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.kyc_document_controller import KycDocumentController
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.kyc_document import (
    DocumentAccessUrl,
    KycDocumentRead,
)
from remitx_api.routes.routers import create_admin_router

router: APIRouter = create_admin_router(
    permission=PermissionCode.KYC_DOCUMENT_READ,
    prefix="/admin/kyc/documents",
    tags=["admin"],
)
controller = KycDocumentController()


@router.get("", response_model=list[KycDocumentRead])
def list_application_documents(application_id: uuid.UUID):
    return controller.list_for_review(application_id)


@router.get("/{document_id}/url", response_model=DocumentAccessUrl)
def get_document_url(
    document_id: uuid.UUID,
    # Not a gate — the router's permission is. The audit entry needs to name
    # whoever looked.
    reviewer: User = Depends(get_current_user),
):
    document, signed = controller.access_url(
        document_id=document_id,
        actor_user_id=reviewer.id,
        as_reviewer=True,
    )
    return DocumentAccessUrl(
        document_id=document.document_id,
        content_type=document.content_type,
        url=signed.url,
        expires_at=signed.expires_at,
    )
