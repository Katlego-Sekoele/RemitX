"""A stokvel's cover photo: metadata only, never the bytes.

The file lives in object storage under one fixed key per stokvel
(``stokvel-covers/<id>``). Replacing the photo overwrites that object.
Keeping the bytes out of Postgres matches KYC documents: a database dump
should not carry members' pictures.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base

# Photographs only. No SVG: a cover is rendered to every member, and an SVG
# is a scriptable document. No GIF or PDF: this is a picture, not a document.
ALLOWED_COVER_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")

MAX_COVER_BYTES = 5 * 1024 * 1024

# Short enough that a replaced photo cannot linger in a shared link, and long
# enough that the member screen's poll refreshes it before it expires.
COVER_URL_TTL_SECONDS = 5 * 60

_COVER_TYPES = ", ".join(f"'{value}'" for value in ALLOWED_COVER_CONTENT_TYPES)


def cover_object_key(stokvel_id: uuid.UUID) -> str:
    """The one object key a stokvel's cover may occupy."""
    return f"stokvel-covers/{stokvel_id}"


class StokvelCover(Base):
    __tablename__ = "stokvel_covers"
    __table_args__ = (
        CheckConstraint(
            f"content_type IN ({_COVER_TYPES})",
            name="stokvel_covers_content_type_valid",
        ),
    )

    stokvel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("stokvels.id"), primary_key=True
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
