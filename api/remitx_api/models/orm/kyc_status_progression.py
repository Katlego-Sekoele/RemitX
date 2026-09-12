"""Legal KYC application status transitions, stored as data."""

import uuid

from sqlalchemy import ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class KycApplicationStatusProgression(Base):
    __tablename__ = "kyc_application_status_progressions"
    __table_args__ = (
        UniqueConstraint(
            "from_status",
            "to_status",
            name="uq_kyc_application_status_progressions_from_to",
        ),
    )

    progression_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    from_status: Mapped[str] = mapped_column(
        Text,
        ForeignKey("kyc_application_statuses.status", ondelete="RESTRICT"),
        nullable=False,
    )
    to_status: Mapped[str] = mapped_column(
        Text,
        ForeignKey("kyc_application_statuses.status", ondelete="RESTRICT"),
        nullable=False,
    )
