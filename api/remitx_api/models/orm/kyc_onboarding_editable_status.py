"""Application statuses in which the applicant may still PATCH a draft.

`submitted` is open (a reviewer can still pick it up) but the applicant must
not keep editing it. That distinction does not fit `kyc_application_statuses.
is_open`, so it lives here rather than as a Python frozenset.
"""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class KycOnboardingEditableStatus(Base):
    __tablename__ = "kyc_onboarding_editable_statuses"

    status: Mapped[str] = mapped_column(
        Text,
        ForeignKey("kyc_application_statuses.status", ondelete="CASCADE"),
        primary_key=True,
    )
