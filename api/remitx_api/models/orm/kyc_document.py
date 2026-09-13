"""Uploaded evidence for a KYC application — metadata only, never the bytes.

The file itself lives in object storage; `storage_path` points at it. Keeping
blobs out of Postgres is partly cost and partly blast radius: a database dump
taken for debugging should not contain somebody's passport scan.

`sha256` is the integrity record a reviewer's decision rests on — it says the
file being looked at is the file that was uploaded — and doubles as the dedup
key, so re-uploading the same scan cannot quietly produce two rows a reviewer
has to compare.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base
from remitx_api.models.orm.kyc_lifecycle import (
    KycDocumentStatus,
    KycDocumentType,
    sql_value_list,
)

# Scans and photographs of documents. No archives, nothing executable, and
# specifically no SVG: a reviewer has to be able to look at the thing in a
# browser, and an SVG is a scriptable document rather than a picture.
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "application/pdf")

MAX_SIZE_BYTES = 10 * 1024 * 1024

# Enough for an identity document, a proof of address, a selfie and evidence
# of source of funds, with room for a reviewer asking for one of them again.
# A cap at all is what stops one bored applicant filling the bucket.
MAX_DOCUMENTS_PER_APPLICATION = 6

SHA256_HEX_LENGTH = 64


def utcnow() -> datetime:
    return datetime.now(UTC)


class KycDocument(Base):
    __tablename__ = "kyc_documents"
    __table_args__ = (
        CheckConstraint(
            f"document_type IN ({sql_value_list(KycDocumentType)})",
            name="kyc_documents_document_type_valid",
        ),
        CheckConstraint(
            "content_type IN ("
            + ", ".join(f"'{value}'" for value in ALLOWED_CONTENT_TYPES)
            + ")",
            name="kyc_documents_content_type_valid",
        ),
        CheckConstraint(
            f"size_bytes > 0 AND size_bytes <= {MAX_SIZE_BYTES}",
            name="kyc_documents_size_bytes_in_range",
        ),
        CheckConstraint(
            f"status IN ({sql_value_list(KycDocumentStatus)})",
            name="kyc_documents_status_valid",
        ),
        CheckConstraint(
            f"sha256 IS NULL OR length(sha256) = {SHA256_HEX_LENGTH}",
            name="kyc_documents_sha256_length",
        ),
        # The invariant the whole two-step upload exists to protect: a row
        # that claims to be stored has been read back out of the bucket and
        # hashed. Enforced here as well as in the controller because a
        # half-applied completion is exactly the bug this would hide.
        CheckConstraint(
            "status <> 'stored' OR (sha256 IS NOT NULL AND stored_at IS NOT NULL)",
            name="kyc_documents_stored_has_digest",
        ),
        # Dedup, and the reason `sha256` is not merely advisory. Pending rows
        # carry no digest and NULLs do not collide, so an abandoned upload
        # never blocks the retry that replaces it.
        Index(
            "uq_kyc_documents_application_sha256",
            "application_id",
            "sha256",
            unique=True,
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("kyc_applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=KycDocumentStatus.PENDING.value,
        default=KycDocumentStatus.PENDING.value,
    )
    # Object-storage key, not a URL: the bucket and any signing are the storage
    # layer's business, and a stored URL would go stale the moment either moved.
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    # BigInteger rather than Integer: a size column that can overflow is a
    # size column that will be believed when it is wrong. Declared at intent,
    # overwritten with the bucket's own answer at completion.
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Null until the object has been read back and hashed — there is nothing
    # honest to put here before that.
    sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The applicant normally, but a reviewer may attach evidence on their
    # behalf (a scan taken in branch), so this is not derivable from the
    # application's user_id.
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # When the upload was *requested*. `stored_at` is when bytes arrived and
    # were verified; the gap between them is how long the applicant took.
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    stored_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @property
    def is_stored(self) -> bool:
        return self.status == KycDocumentStatus.STORED.value
