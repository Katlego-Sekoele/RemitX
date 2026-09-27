"""Application user, mirrored from Clerk.

Clerk owns credentials and profile data. This table exists so domain records
(beneficiaries, wallets, transfers) have a stable local foreign key, and so
queries can join on identity without calling out to Clerk.

Rows are created just-in-time on the first authenticated request — see
remitx_api/controllers/user_controller.py.

Identity, not authority: nothing here says what a user may do. Staff access
lives in the RBAC tables (user_roles -> role_permissions -> permissions) and
is enforced per route by auth.permissions.RequirePermission.

No KYC state here either. `kyc_applications` owns it, and a user's KYC
standing is *derived* from their applications on read — see
`KycApplicationRepository.get_standing`. There is deliberately no denormalised
`kyc_status` copy on this table: one authoritative place beats a copy that can
disagree with it. `suspended_at` is the exception that is not a copy — nothing
in the KYC tables says "this account is stopped", so it lives here.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


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


def short_display_name(first_name: str | None, last_name: str | None) -> str | None:
    """How one customer is named to another in history and receipts:
    "Tendai M.", or just "Tendai" with no last name on file. None when there
    is no first name either, so callers can fall back to neutral wording.
    """
    first = (first_name or "").strip()
    if not first:
        return None
    last = (last_name or "").strip()
    return f"{first} {last[0].upper()}." if last else first


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
    # First name as reported by Clerk. Stored only to build `base_reference`'s
    # human-readable prefix — display-name concerns otherwise stay with
    # Clerk. Nullable for the same reason `email` is: not every sign-in
    # strategy yields one.
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Not yet resolved from Clerk anywhere (no `resolve_last_name` callable
    # exists alongside `resolve_first_name`/`resolve_email` in
    # UserController.ensure_provisioned) — always NULL for now. Added so
    # BeneficiaryController can join a beneficiary's last name from here
    # instead of storing a second, driftable copy on `Beneficiary` (see
    # models/orm/beneficiary.py); populating it at signup is a separate,
    # not-yet-built change.
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The verified name and residence (ISO 3166-1 alpha-2) from the user's
    # latest approved KYC application, written in the same transaction as the
    # approval (`KycApplicationRepository.apply_transition`). A copy, but of
    # identity rather than KYC standing: row-level security keeps a customer
    # route from reading anyone else's application, and a sender's
    # beneficiary list has to show the verified name. NULL until approved;
    # display falls back to `first_name`.
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # Contact mobile, E.164, edited on the profile page. Clerk's sign-in
    # strategies do not require a phone, so it lives here. Not identity
    # evidence: editing it never overwrites the verified mobile on the
    # approved `kyc_applications` row, though an approval seeds this field
    # from that row the same way it seeds `full_name` and `country`
    # (`UserRepository.record_verified_identity`), so a profile edit
    # afterwards is what wins going forward.
    mobile_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when compliance stops the account (`user:suspend`). Deliberately not
    # part of the KYC state machine: a suspended user may well be KYC-approved,
    # and lifting the suspension should not have to reconstruct where their
    # application had got to. Nullable because NULL is the normal case.
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
