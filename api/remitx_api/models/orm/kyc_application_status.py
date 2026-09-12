"""Catalogue of statuses a KYC application row may hold."""

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class KycApplicationStatusRecord(Base):
    __tablename__ = "kyc_application_statuses"

    status: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
