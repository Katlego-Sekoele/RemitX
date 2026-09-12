"""Append-only log of every KYC status change.

Each row records the status the application held from this point forward.
The prior status is the previous row for the same application, ordered by
``made_at`` — no ``from_status`` column required.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class KycDecisionHistory(Base):
    __tablename__ = "kyc_decision_history"
    __table_args__ = (
        Index(
            "idx_kyc_decision_history_application_made_at",
            "application_id",
            "made_at",
        ),
    )

    history_id: Mapped[uuid.UUID] = mapped_column(
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
    status: Mapped[str] = mapped_column(
        Text,
        ForeignKey("kyc_application_statuses.status", ondelete="RESTRICT"),
        nullable=False,
    )
    reason_code: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("kyc_reason_codes.reason_code", ondelete="RESTRICT"),
        nullable=True,
    )
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    made_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    made_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
