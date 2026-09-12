"""Application user, mirrored from Clerk.

Clerk owns credentials and profile data. This table exists so domain records
(beneficiaries, wallets, transfers) have a stable local foreign key, and so
queries can join on identity without calling out to Clerk.

Rows are created just-in-time on the first authenticated request — see
remitx_api/controllers/user_controller.py.

Identity, not authority: nothing here says what a user may do. Staff access
lives in the RBAC tables (user_roles -> role_permissions -> permissions) and
is enforced per route by auth.permissions.RequirePermission.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base

KYC_UNVERIFIED = "UNVERIFIED"
KYC_APPROVED = "APPROVED"
KYC_STATUSES = (KYC_UNVERIFIED, KYC_APPROVED)


def utcnow() -> datetime:
    return datetime.now(UTC)


def reference_base(first_name: str | None) -> str:
    """The lowercase, <=8-char, letters-and-digits-only name part of a
    `User.base_reference` — e.g. "Sian" -> "sian".
    `UserRepository.next_base_reference` appends the number that
    disambiguates same-named users (the second "Sian" to sign up gets
    "sian2"). Falls back to "user" when no first name is available, e.g.
    Clerk gave neither a claim nor a profile lookup hit.
    """
    cleaned = "".join(ch for ch in (first_name or "") if ch.isalnum())
    return (cleaned[:8] or "user").lower()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "kyc_status IN ('UNVERIFIED', 'APPROVED')",
            name="users_kyc_status_valid",
        ),
    )

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
    # First name as reported by Clerk. Stored only to build `base_reference`'s
    # human-readable prefix — display-name concerns otherwise stay with
    # Clerk. Nullable for the same reason `email` is: not every sign-in
    # strategy yields one.
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # `reference_base(first_name)` plus a disambiguating number, e.g.
    # "sian1". Assigned once at signup by
    # `UserRepository.next_base_reference`. Not itself an EFT-matchable
    # reference — every one of this user's `Account.reference` values
    # (Transaction_Flow_Context.md §1) is built by appending a currency
    # suffix to this, e.g. "sian1-zar", "sian1-tok".
    base_reference: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        index=True,
    )
    # Real KYC (document intake, admin review queue) is out of this
    # prototype's scope — see docs/project-brief.md. This is a minimal
    # toggle: UNVERIFIED users are rejected outright by quote/remittance
    # creation regardless of the numeric limit (brief's Unverified tier is
    # ZAR 0/0), APPROVED users are subject only to the numeric limits.
    kyc_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=KYC_UNVERIFIED,
        server_default=KYC_UNVERIFIED,
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
