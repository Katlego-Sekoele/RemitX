"""What a wizard step needs before it counts as complete.

A row is either a column on `kyc_applications` or a stored document type.
`required_when` is data so PEP follow-ups and `source_of_funds = other` do not
become `if step == "declarations"` in the service. `copy_on_resubmit` is the
resubmission pre-fill list — also data, so a new declared field is copied once
it has a row here.
"""

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base

REQUIREMENT_KINDS = ("field", "document")
REQUIRED_WHEN = (
    "always",
    "declares_pep",
    "source_of_funds_other",
    "id_requires_expiry",
    "never",
)


class KycOnboardingRequirement(Base):
    __tablename__ = "kyc_onboarding_requirements"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('field', 'document')",
            name="kyc_onboarding_requirements_kind_valid",
        ),
        CheckConstraint(
            "required_when IN ('always', 'declares_pep', "
            "'source_of_funds_other', 'id_requires_expiry', 'never')",
            name="kyc_onboarding_requirements_when_valid",
        ),
    )

    step: Mapped[str] = mapped_column(
        Text,
        ForeignKey("kyc_onboarding_steps.step", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    required_when: Mapped[str] = mapped_column(Text, nullable=False, default="always")
    copy_on_resubmit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
