"""Read schemas for KYC documents.

Nothing here carries PII — a document row holds a type, a size, a digest and
two UUIDs — so unlike `schemas/kyc.py` there is no masked/unmasked pair. The
one field deliberately withheld is `storage_path`: the object key is not
secret, but it is also not the client's business, and a key that never reaches
a browser is a key that never ends up in a bug report.

There is no upload *request* schema. The body of an upload is the file itself,
so what would be its fields — the application, the document type — arrive as
query parameters and are declared on the route.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer


def _utc_isoformat(value: datetime | None) -> str | None:
    """Always emit an offset, whatever the backend stored — see
    schemas/integration_message.py for why SQLite makes this necessary."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class KycDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    application_id: uuid.UUID
    document_type: str
    status: str
    content_type: str
    size_bytes: int
    sha256: str | None = None
    uploaded_by_user_id: uuid.UUID
    uploaded_at: datetime
    stored_at: datetime | None = None
    # Whether the applicant may still remove it: never once a reviewer has
    # been given it. Always false on staff routes.
    removable: bool = False

    @field_serializer("uploaded_at", "stored_at")
    def _as_utc(self, value: datetime | None) -> str | None:
        return _utc_isoformat(value)


class DocumentAccessUrl(BaseModel):
    """A read URL good for minutes. There is no long-lived alternative."""

    document_id: uuid.UUID
    content_type: str
    url: str
    expires_at: datetime

    @field_serializer("expires_at")
    def _as_utc(self, value: datetime) -> str | None:
        return _utc_isoformat(value)
