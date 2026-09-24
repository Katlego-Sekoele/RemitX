"""
A user's external bank account — the destination for a withdrawal.

"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base

STATUS_PENDING_VERIFICATION = "pending_verification"
STATUS_VERIFIED = "verified"
STATUS_REJECTED = "rejected"

BANK_ACCOUNT_STATUSES = (
    STATUS_PENDING_VERIFICATION,
    STATUS_VERIFIED,
    STATUS_REJECTED,
)


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_verification','verified','rejected')",
            name="bank_accounts_status_valid",
        ),
    )

    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    account_holder_name: Mapped[str] = mapped_column(Text, nullable=False)
    bank_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Account no. not encrypted or masked because this is only a prototype
    # simulating cash-out
    account_number: Mapped[str] = mapped_column(Text, nullable=False)
    branch_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Must match the currency of the user's account being withdrawn from
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=STATUS_PENDING_VERIFICATION,
        server_default=STATUS_PENDING_VERIFICATION,
    )
    verified_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set only on rejection — the reason an admin gave, shown back to the user.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
