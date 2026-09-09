"""Application user, mirrored from Clerk.

Clerk owns credentials and profile data. This table exists so domain records
(beneficiaries, wallets, transfers) have a stable local foreign key, and so
queries can join on identity without calling out to Clerk.

Rows are created just-in-time on the first authenticated request — see
remitx_api/controllers/user_controller.py.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def reference_base(first_name: str | None) -> str:
    """The lowercase, <=8-char, letters-and-digits-only prefix of a
    `User.reference` — e.g. "Sian" -> "sian". `UserRepository.next_reference`
    appends the number that disambiguates same-named senders (the second
    "Sian" to sign up gets "sian2"). Falls back to "user" when no first name
    is available, e.g. Clerk gave neither a claim nor a profile lookup hit.
    """
    cleaned = "".join(ch for ch in (first_name or "") if ch.isalnum())
    return (cleaned[:8] or "user").lower()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    # Clerk's `sub` claim. Unique so just-in-time provisioning can rely on the
    # database to arbitrate concurrent first requests from the same caller.
    clerk_user_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        index=True,
    )
    # Nullable: not every Clerk sign-in strategy yields an email claim.
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    # First name as reported by Clerk. Stored only to build `reference`'s
    # human-readable prefix — display-name concerns otherwise stay with
    # Clerk. Nullable for the same reason `email` is: not every sign-in
    # strategy yields one.
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The sender's permanent EFT reference (Transaction_Flow_Context.md
    # Phase A): `reference_base(first_name)` plus a disambiguating number,
    # e.g. "sian1". Assigned once at signup by
    # `UserRepository.next_reference`, quoted on every deposit, and how
    # deposit_service attributes an unregistered bank statement line to this
    # user — there is no per-deposit reference to match on instead.
    reference: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        index=True,
    )
    # Set in Python rather than by the database: SQLite's CURRENT_TIMESTAMP has
    # only second precision, which is too coarse to order rapid inserts.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
