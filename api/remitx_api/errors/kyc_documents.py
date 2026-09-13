"""Errors raised by the KYC document upload and retrieval flow."""

from __future__ import annotations

from remitx_api.errors.base import ConflictError, DomainError, NotFoundError


class UnknownKycDocumentError(NotFoundError):
    """No document with that id that this caller is allowed to know about.

    Deliberately the same error whether the document does not exist or belongs
    to somebody else: a 403 on another applicant's document id confirms it
    exists, which is most of what an enumeration attack wants.
    """


class UnsupportedDocumentTypeError(DomainError):
    """The content type is not one a reviewer can safely be shown.

    Raised both when a client declares a type outside the allowlist and when
    the bytes that arrive turn out to be a different type than declared.
    """


class DocumentTooLargeError(DomainError):
    """Bigger than the per-file cap, declared or actual."""

    # Spelled out rather than imported: Starlette renamed this constant, and
    # the API pins neither version.
    status_code = 413


class EmptyUploadError(DomainError):
    """The request carried no body. Not a 413 — nothing was too large."""


class DocumentLimitReachedError(ConflictError):
    """This application already holds as many documents as it may."""


class ApplicationClosedToDocumentsError(ConflictError):
    """The application has reached an outcome; its evidence is now fixed."""


class UploadNotVerifiedError(ConflictError):
    """The object in the bucket is not the one that was declared.

    Covers a missing object (nothing was ever uploaded), a size that does not
    match the declaration, and content whose sniffed type contradicts it. The
    row stays `pending` and the object, if any, is removed.
    """


class DuplicateDocumentError(ConflictError):
    """This exact file is already attached to the application."""


class DocumentNotStoredError(ConflictError):
    """The upload never completed, so there is nothing to hand back.

    A `pending` row is an intent, not evidence. No retrieval path serves one —
    which is what makes an abandoned upload harmless rather than a document
    nobody verified.
    """
