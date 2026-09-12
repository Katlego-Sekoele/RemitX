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
from remitx_api.models.orm.kyc_lifecycle import KycDocumentType, sql_value_list

# Scans and photographs of documents. No archives and nothing executable: a
# reviewer has to be able to look at the thing in a browser.
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp", "application/pdf")

MAX_SIZE_BYTES = 10 * 1024 * 1024

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
            f"length(sha256) = {SHA256_HEX_LENGTH}",
            name="kyc_documents_sha256_length",
        ),
        # Dedup, and the reason `sha256` is not merely advisory.
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
    # Object-storage key, not a URL: the bucket and any signing are the storage
    # layer's business, and a stored URL would go stale the moment either moved.
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    # BigInteger rather than Integer: a size column that can overflow is a
    # size column that will be believed when it is wrong.
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    # The applicant normally, but a reviewer may attach evidence on their
    # behalf (a scan taken in branch), so this is not derivable from the
    # application's user_id.
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
