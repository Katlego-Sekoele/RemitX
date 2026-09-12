"""Static catalogue of KYC reviewer reason codes."""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class KycReasonCodeRecord(Base):
    __tablename__ = "kyc_reason_codes"

    reason_code: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
