"""Upload, verification and audited retrieval of KYC evidence.

The upload is one call. The browser POSTs the file to the API, and the API —
holding the actual bytes — checks them before anything reaches storage:

1. The application is the caller's own and still open, and it is not already
   at its document limit.
2. The declared content type is on the allowlist, and the bytes agree: the
   type is read from the file's leading bytes, not from the header the client
   sent or from a filename.
3. The SHA-256 is computed and checked against the application's other
   documents, so the same scan cannot arrive twice.
4. A `pending` row is written, the object is put in the bucket under that
   row's key, and only then is the row marked `stored`.

Step 4 is in that order so a failure can only ever cost us a `pending` row.
Putting the object first and writing the row second would, on a failed insert,
leave an object in the bucket that the database has never heard of — and an
orphan object is invisible to every access control this system has.

Validating bytes we hold is the whole point of routing the upload through the
API: there is no window in which unchecked content sits in the bucket, and no
declaration to take on trust. What it costs is that the API carries the bytes,
which is why `services/upload_stream.py` refuses an oversized body while it
arrives rather than after.

Retrieval does not return bytes through the API: `access_url` hands back a
read URL that expires in minutes, and writes an audit entry first — for a
reviewer and applicant alike, because "who looked at whose identity document"
is a question POPIA expects an answer to.

Deleting an application does not delete its documents. FICA §23 retention runs
five years from the end of the relationship, so removal is a lifecycle concern
and nothing here offers it. The one object this controller deletes is one whose
row could not be completed, and which was therefore never evidence of anything.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from remitx_api.db.transaction import db_transaction
from remitx_api.errors.kyc import UnknownKycApplicationError
from remitx_api.errors.kyc_documents import (
    ApplicationClosedToDocumentsError,
    DocumentLimitReachedError,
    DocumentNotStoredError,
    DocumentTooLargeError,
    DuplicateDocumentError,
    UnknownKycDocumentError,
    UnsupportedDocumentTypeError,
    UploadNotVerifiedError,
)
from remitx_api.errors.storage import ObjectStorageError
from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
from remitx_api.models.orm.kyc_application import KycApplication
from remitx_api.models.orm.kyc_document import (
    ALLOWED_CONTENT_TYPES,
    MAX_DOCUMENTS_PER_APPLICATION,
    MAX_SIZE_BYTES,
    KycDocument,
)
from remitx_api.models.orm.kyc_lifecycle import (
    OPEN_STATUSES,
    KycDocumentStatus,
    KycDocumentType,
    KycStatus,
)
from remitx_api.repositories.kyc_application_repository import (
    KycApplicationRepository,
)
from remitx_api.repositories.kyc_document_repository import KycDocumentRepository
from remitx_api.services.audit_service import record_audit
from remitx_api.services.file_signatures import (
    CONTENT_TYPE_SVG,
    SNIFF_LENGTH,
    sniff_content_type,
)
from remitx_api.services.object_storage import ObjectStorage, object_storage

logger = logging.getLogger(__name__)

# Five minutes: long enough to open a PDF, short enough that a URL pasted into
# a chat is dead before anyone clicks it.
ACCESS_URL_TTL_SECONDS = 5 * 60


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SignedUrl:
    """A URL and the moment it stops working."""

    url: str
    expires_at: datetime


def storage_path_for(application_id: uuid.UUID, document_id: uuid.UUID) -> str:
    """`kyc/{application}/{document}` — two UUIDv4s and nothing else.

    Object keys turn up in storage access logs, in metrics, and in any URL
    that gets pasted into a chat. A key like `kyc/naidoo-8801015009087-id.pdf`
    would leak an identity number through channels no other control covers, so
    the key carries no name, no identity number, no email, and nothing
    guessable.
    """
    return f"kyc/{application_id}/{document_id}"


class KycDocumentController:
    def __init__(self, storage: ObjectStorage | None = None) -> None:
        self._documents = KycDocumentRepository()
        self._applications = KycApplicationRepository()
        self._storage = storage

    @property
    def storage(self) -> ObjectStorage:
        # Resolved per call rather than in __init__: controllers are built at
        # import time by the route modules, long before a request proves the
        # deployment has a bucket configured.
        return self._storage or object_storage()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def store_document(
        self,
        *,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
        document_type: KycDocumentType,
        declared_content_type: str,
        body: bytes,
    ) -> KycDocument:
        """Validate an uploaded file and put it in the bucket."""
        application = self._require_own_application(application_id, user_id)

        if KycStatus(application.status) not in OPEN_STATUSES:
            raise ApplicationClosedToDocumentsError(
                "This application has reached an outcome; start a new one to "
                "supply further documents."
            )

        if declared_content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedDocumentTypeError(
                f"{declared_content_type or 'An unnamed content type'} is not an "
                f"accepted document type. Upload one of: "
                f"{', '.join(ALLOWED_CONTENT_TYPES)}."
            )

        # Defence in depth: the route refuses an oversized body while it is
        # still arriving, so reaching this with too many bytes would mean that
        # check was bypassed rather than that a client sent too much.
        if len(body) > MAX_SIZE_BYTES:
            raise DocumentTooLargeError(
                f"Documents are limited to {MAX_SIZE_BYTES // (1024 * 1024)} MB."
            )

        if (
            self._documents.count_for_application(application_id)
            >= MAX_DOCUMENTS_PER_APPLICATION
        ):
            raise DocumentLimitReachedError(
                f"This application already has {MAX_DOCUMENTS_PER_APPLICATION} "
                "documents. Remove one or contact support before adding another."
            )

        content_type = self._identify(body, declared_content_type)
        digest = hashlib.sha256(body).hexdigest()

        if self._documents.find_stored_by_digest(application_id, digest):
            raise DuplicateDocumentError(
                "This file is already attached to the application."
            )

        document = self._reserve(
            application_id=application_id,
            user_id=user_id,
            document_type=document_type,
            content_type=content_type,
            size_bytes=len(body),
        )
        self._store(document, body, digest)
        return document

    def _identify(self, body: bytes, declared_content_type: str) -> str:
        """The content type of these bytes, or a refusal that says why.

        A declared type is a client assertion and a filename is a naming
        convention; neither is evidence. This is the only thing that decides
        what the file is, and the declaration is held to it.
        """
        sniffed = sniff_content_type(body[:SNIFF_LENGTH])

        if sniffed == CONTENT_TYPE_SVG:
            raise UnsupportedDocumentTypeError(
                "SVG files are not accepted: they can carry scripts, and "
                "documents are rendered back to reviewers."
            )

        if sniffed is None or sniffed not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedDocumentTypeError(
                "The uploaded file is not a PDF, JPEG, PNG or WebP image."
            )

        if sniffed != declared_content_type:
            raise UnsupportedDocumentTypeError(
                f"The uploaded file is {sniffed}, not the declared "
                f"{declared_content_type}."
            )

        return sniffed

    @db_transaction
    def _reserve(
        self,
        *,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        document_type: KycDocumentType,
        content_type: str,
        size_bytes: int,
    ) -> KycDocument:
        """Claim the row, and with it the object key, before writing bytes.

        Committed on its own rather than inside one transaction around the
        whole upload: the row is what makes an object in the bucket reachable
        by anything, so it has to be durable before the object exists.

        No digest yet. A `pending` row carrying one would collide, through the
        unique index on (application_id, sha256), with the retry that replaces
        it — so the file that failed to store would be the one file the
        applicant could never upload.
        """
        document_id = uuid.uuid4()
        return self._documents.add(
            KycDocument(
                document_id=document_id,
                application_id=application_id,
                document_type=document_type.value,
                status=KycDocumentStatus.PENDING.value,
                storage_path=storage_path_for(application_id, document_id),
                content_type=content_type,
                size_bytes=size_bytes,
                uploaded_by_user_id=user_id,
            )
        )

    @db_transaction
    def _store(self, document: KycDocument, body: bytes, digest: str) -> None:
        """Put the object, confirm it landed, and promote the row.

        A `pending` row whose object never arrived is the shape every failure
        here takes: nothing serves it, no reviewer sees it, and the applicant
        can upload the same file again.
        """
        try:
            self.storage.put_object(
                document.storage_path,
                body,
                content_type=document.content_type,
            )
        except ObjectStorageError:
            logger.exception("Storing KYC document %s failed", document.document_id)
            raise

        # S3 rejects a truncated body, so a put that did not raise already
        # implies this. The check is what makes `stored` mean "we have seen the
        # object in the bucket" rather than "the client library did not raise".
        stored = self.storage.stat(document.storage_path)
        if stored is None or stored.size_bytes != document.size_bytes:
            self._discard(document)
            raise UploadNotVerifiedError(
                "The uploaded file did not store correctly. Please try again."
            )

        document.sha256 = digest
        document.status = KycDocumentStatus.STORED.value
        document.stored_at = utcnow()
        try:
            db.session.flush()
        except IntegrityError as exc:
            # The unique index caught a duplicate that the read before the
            # upload raced past. The object is ours to clean up: nothing will
            # point at it.
            self._discard(document)
            raise DuplicateDocumentError(
                "This file is already attached to the application."
            ) from exc

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def list_own_documents(
        self,
        *,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
    ) -> list[KycDocument]:
        self._require_own_application(application_id, user_id)
        return self._documents.list_for_application(application_id)

    def list_for_review(self, application_id: uuid.UUID) -> list[KycDocument]:
        """A reviewer sees verified evidence only: a `pending` row is an
        intent nobody has checked, and showing it invites a decision on it."""
        if self._applications.get_by_id(application_id) is None:
            raise UnknownKycApplicationError(
                f"No KYC application with id {application_id}."
            )
        return self._documents.list_for_application(application_id, stored_only=True)

    @db_transaction
    def access_url(
        self,
        *,
        document_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        as_reviewer: bool = False,
    ) -> tuple[KycDocument, SignedUrl]:
        """A short-lived read URL, and the audit entry that records issuing it.

        `as_reviewer` says the caller has already been gated on
        `kyc:document:read` by the router; everybody else may only reach their
        own documents. Both paths are audited — a reviewer's read is the one
        POPIA cares about, and an applicant's is cheap to record alongside it.
        """
        if as_reviewer:
            document = self._documents.get_by_id(document_id)
            if document is None:
                raise UnknownKycDocumentError(f"No KYC document with id {document_id}.")
        else:
            document = self._require_own_document(document_id, actor_user_id)

        if not document.is_stored:
            raise DocumentNotStoredError(
                "This upload was never completed, so there is no file to view."
            )

        signed = SignedUrl(
            url=self.storage.presign_get(
                document.storage_path,
                content_type=document.content_type,
                expires_in=ACCESS_URL_TTL_SECONDS,
                # Named after the document's id and type, never the applicant:
                # a filename lands in the reviewer's download history.
                download_name=f"{document.document_type}-{document.document_id}",
            ),
            expires_at=utcnow() + timedelta(seconds=ACCESS_URL_TTL_SECONDS),
        )

        record_audit(
            actor_user_id=actor_user_id,
            action=AuditAction.KYC_DOCUMENT_VIEWED,
            subject_type=AuditSubject.KYC_DOCUMENT,
            subject_id=document.document_id,
            after={
                "application_id": str(document.application_id),
                "document_type": document.document_type,
                "as_reviewer": as_reviewer,
            },
        )
        return document, signed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_own_application(
        self,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> KycApplication:
        application = self._applications.get_by_id(application_id)
        if application is None or application.user_id != user_id:
            # Same answer whether it does not exist or belongs to somebody
            # else: a 403 on another applicant's id confirms that id is real.
            raise UnknownKycApplicationError(
                f"No KYC application with id {application_id}."
            )
        return application

    def _require_own_document(
        self,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> KycDocument:
        document = self._documents.get_by_id(document_id)
        if document is None:
            raise UnknownKycDocumentError(f"No KYC document with id {document_id}.")
        application = self._applications.get_by_id(document.application_id)
        if application is None or application.user_id != user_id:
            raise UnknownKycDocumentError(f"No KYC document with id {document_id}.")
        return document

    def _discard(self, document: KycDocument) -> None:
        """Remove an object whose row was never completed.

        The row stays `pending` as the record that an upload was attempted; the
        object goes, because bytes nothing points at are bytes no access
        control reaches.
        """
        try:
            self.storage.delete(document.storage_path)
        except ObjectStorageError:
            # Never mask the original failure with a cleanup failure: the
            # caller needs to hear why their upload was refused.
            logger.warning(
                "Could not remove unverified upload %s", document.document_id
            )
