"""Append-only lifecycle history for a KYC application row.

Each row is a snapshot of the application after a change: status, version, and
outcome fields. The status before this row is whatever the previous row held,
ordered by ``changed_at``.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, SmallInteger, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


class KycApplicationHistory(Base):
    __tablename__ = "kyc_application_history"
    __table_args__ = (
        Index(
            "idx_kyc_application_history_application_changed_at",
            "application_id",
            "changed_at",
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
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_rating: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier_granted: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reason_code: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("kyc_reason_codes.reason_code", ondelete="RESTRICT"),
        nullable=True,
    )
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
