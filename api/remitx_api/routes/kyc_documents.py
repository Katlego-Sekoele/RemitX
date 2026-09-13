"""Applicant-facing KYC document endpoints.

The upload is a POST of the file itself: the body is the document, and the
metadata that would otherwise be multipart fields arrives as query parameters.
`fetch(url, {method: "POST", body: file})` sets `Content-Type` and
`Content-Length` from the `File` without the caller doing anything, and the
server keeps control of how many bytes it is willing to read —
`services/upload_stream.py` explains why that matters more than the
convention.

This is the one `async def` route in the API. Reading the request stream is
async, so the handler has to be; everything after it — the database and the
bucket, both synchronous — runs in a worker thread exactly like every other
route, rather than blocking the event loop for the length of an upload.

Every route here is scoped to the caller's own application. Ownership is
checked in the controller, so a document id belonging to somebody else answers
404 rather than confirming it exists.
"""

import uuid

from fastapi import APIRouter, Depends, Request, status
from fastapi.concurrency import run_in_threadpool

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.kyc_document_controller import KycDocumentController
from remitx_api.models.orm.kyc_document import MAX_SIZE_BYTES
from remitx_api.models.orm.kyc_lifecycle import KycDocumentType
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.kyc_document import (
    DocumentAccessUrl,
    KycDocumentRead,
)
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.upload_stream import read_upload

router: APIRouter = create_customer_router(prefix="/kyc/documents", tags=["kyc"])
controller = KycDocumentController()


@router.post(
    "",
    response_model=KycDocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    application_id: uuid.UUID,
    document_type: KycDocumentType,
    user: User = Depends(get_current_user),
):
    """Accept one file, validate it, and store it.

    No body parameter is declared, so the framework leaves the request stream
    alone and `read_upload` decides how much of it is read.
    """
    body = await read_upload(
        request.stream(),
        limit=MAX_SIZE_BYTES,
        content_length=request.headers.get("content-length"),
    )

    return await run_in_threadpool(
        controller.store_document,
        user_id=user.id,
        application_id=application_id,
        document_type=document_type,
        # A client assertion, held to the file's leading bytes by the
        # controller. Browsers set it from the File's own type.
        declared_content_type=request.headers.get("content-type", ""),
        body=body,
    )


@router.get("", response_model=list[KycDocumentRead])
def list_my_documents(
    # Bare scalar: FastAPI reads it from the query string, and Query()
    # as a default trips B008.
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    return controller.list_own_documents(
        user_id=user.id,
        application_id=application_id,
    )


@router.get("/{document_id}/url", response_model=DocumentAccessUrl)
def get_my_document_url(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    document, signed = controller.access_url(
        document_id=document_id,
        actor_user_id=user.id,
    )
    return DocumentAccessUrl(
        document_id=document.document_id,
        content_type=document.content_type,
        url=signed.url,
        expires_at=signed.expires_at,
    )
