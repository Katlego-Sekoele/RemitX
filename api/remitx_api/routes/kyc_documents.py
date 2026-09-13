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
from remitx_api.models.orm.kyc_document import ALLOWED_CONTENT_TYPES, MAX_SIZE_BYTES
from remitx_api.models.orm.kyc_lifecycle import KycDocumentType
from remitx_api.models.orm.user import User
from remitx_api.models.schemas.kyc_document import (
    DocumentAccessUrl,
    KycDocumentRead,
)
from remitx_api.openapi import Tag, error_responses
from remitx_api.routes.routers import create_customer_router
from remitx_api.services.upload_stream import read_upload

router: APIRouter = create_customer_router(
    prefix="/kyc/documents", tags=[Tag.KYC_DOCUMENTS]
)
controller = KycDocumentController()


@router.post(
    "",
    response_model=KycDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a KYC document",
    responses=error_responses(400, 404, 409, 413, 502, 503),
    # The handler reads the stream itself, so FastAPI cannot infer the body.
    # Declared by hand so the generated client takes a File and sends it raw.
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                content_type: {"schema": {"type": "string", "format": "binary"}}
                for content_type in ALLOWED_CONTENT_TYPES
            },
        }
    },
)
async def upload_document(
    request: Request,
    application_id: uuid.UUID,
    document_type: KycDocumentType,
    user: User = Depends(get_current_user),
):
    """The body is the file itself, sent with its own ``Content-Type``. The
    type is checked against the file's leading bytes before it is stored.

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


@router.get(
    "",
    response_model=list[KycDocumentRead],
    summary="List the caller's KYC documents",
    responses=error_responses(404),
)
def list_my_documents(
    # Bare scalar: FastAPI reads it from the query string, and Query()
    # as a default trips B008.
    application_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Metadata only, never the bytes, for one of the caller's applications."""
    documents = controller.list_own_documents(
        user_id=user.id,
        application_id=application_id,
    )
    removable = controller.removable_document_ids(
        user_id=user.id,
        application_id=application_id,
    )
    return [
        KycDocumentRead.model_validate(document).model_copy(
            update={"removable": document.document_id in removable}
        )
        for document in documents
    ]


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a KYC document",
    responses=error_responses(404, 409),
)
def remove_my_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """Only while no reviewer has seen it."""
    controller.remove_document(user_id=user.id, document_id=document_id)


@router.get(
    "/{document_id}/url",
    response_model=DocumentAccessUrl,
    summary="Get a short-lived link to a KYC document",
    responses=error_responses(404, 409, 502, 503),
)
def get_my_document_url(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
):
    """A signed URL that expires in minutes. Every one issued is audited."""
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
