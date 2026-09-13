"""The KYC wizard's steps, as a catalogue rather than a tuple in code.

`next_step` walks these rows in `position` order. Adding a step is an INSERT,
not a release — the frontend still has to grow a route for a new `step` key,
but the server will not silently invent an order the database does not hold.
"""

from sqlalchemy import CheckConstraint, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base

STEP_ROLES = ("entry", "collect", "review", "outcome")


class KycOnboardingStep(Base):
    __tablename__ = "kyc_onboarding_steps"
    __table_args__ = (
        CheckConstraint(
            "role IN ('entry', 'collect', 'review', 'outcome')",
            name="kyc_onboarding_steps_role_valid",
        ),
        CheckConstraint(
            "position >= 0",
            name="kyc_onboarding_steps_position_non_negative",
        ),
    )

    step: Mapped[str] = mapped_column(Text, primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, unique=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
