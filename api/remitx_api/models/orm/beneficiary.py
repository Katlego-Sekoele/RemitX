"""
A sender's beneficiary contact.

first_name/last_name/email/mobile_number/country are deliberately NOT
columns on this table — they're read from the linked User via a join
wherever a Beneficiary is displayed (see BeneficiaryController). Storing a
copy would go stale the moment a user updates their own details (marriage,
correction, moving, etc.) with no way to propagate the update to every
sender's beneficiary list. All of these are properties of the *person*, not
of any one sender's relationship to them, so User is the right place for
them to live regardless of how many senders have added that person as a
beneficiary.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base
from remitx_api.models.orm.account import PAYOUT_CURRENCIES

RELATIONSHIP_PARTNER = "partner"
RELATIONSHIP_PARENT = "parent"
RELATIONSHIP_CHILD = "child"
RELATIONSHIP_SIBLING = "sibling"
RELATIONSHIP_RELATIVE = "relative"
RELATIONSHIP_FRIEND = "friend"
RELATIONSHIP_EMPLOYEE = "employee"
RELATIONSHIP_OTHER = "other"

RELATIONSHIPS = (
    RELATIONSHIP_PARTNER,
    RELATIONSHIP_PARENT,
    RELATIONSHIP_CHILD,
    RELATIONSHIP_SIBLING,
    RELATIONSHIP_RELATIVE,
    RELATIONSHIP_FRIEND,
    RELATIONSHIP_EMPLOYEE,
    RELATIONSHIP_OTHER,
)

_RELATIONSHIP_CHECK_VALUES = ", ".join(f"'{value}'" for value in RELATIONSHIPS)
_PAYOUT_CURRENCY_CHECK_VALUES = ", ".join(f"'{value}'" for value in PAYOUT_CURRENCIES)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Beneficiary(Base):
    """ORM model for the `beneficiaries` table."""

    __tablename__ = "beneficiaries"
    __table_args__ = (
        # "mobile_number or email required" (brief) is enforced in
        # BeneficiaryController.create instead of a DB CHECK.
        CheckConstraint(
            f"relationship IN ({_RELATIONSHIP_CHECK_VALUES})",
            name="beneficiaries_relationship_valid",
        ),
        # payout_currency must be one of the allowed values
        CheckConstraint(
            f"payout_currency IN ({_PAYOUT_CURRENCY_CHECK_VALUES})",
            name="beneficiaries_payout_currency_valid",
        ),
    )
    beneficiary_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    # The sender who added this contact.
    sender_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    # The registered platform user this contact resolves to.
    linked_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )
    # The fiat currency this beneficiary prefers to eventually cash out to.
    payout_currency: Mapped[str] = mapped_column(Text, nullable=False)
    relationship: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
