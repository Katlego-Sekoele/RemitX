"""Append-only record of every risk rating and tier change on an application.

Each row records one change: either a risk rating (`computed_risk_rating` →
`final_risk_rating`) or a tier (`computed_tier` → `final_tier`), never both. The
database insists on a `reason` wherever computed and final differ. Three
writers:

- **Submission** scores the application: computed = the band the score fell
  in, with the score and — in `kyc_assessment_audit_signals` — the signals that
  fired. Final is the same, unless a reviewer override still stands from an
  earlier round, in which case final is the override and the reason is the
  override's.
- **A reviewer override**: computed = the scored rating, final = the reviewer's
  rating, reason mandatory.
- **Approval**: computed = the default tier, final = the tier granted, reason
  mandatory if an officer granted a different one.

The general privileged-action audit log (issue #54) is a separate, wider
thing; this table answers "why is this customer rated and tiered the way they
are?" for one application without joining anything else.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


class KycAssessmentAudit(Base):
    __tablename__ = "kyc_assessment_audit"
    __table_args__ = (
        CheckConstraint(
            "(final_risk_rating IS NULL) <> (final_tier IS NULL)",
            name="kyc_assessment_audit_one_subject",
        ),
        # "The override reason where they differ", enforced by the database. A
        # NULL computed value (never scored) counts as differing.
        CheckConstraint(
            "reason IS NOT NULL OR ("
            "(final_risk_rating IS NULL OR "
            "(computed_risk_rating IS NOT NULL "
            "AND computed_risk_rating = final_risk_rating)) "
            "AND (final_tier IS NULL OR "
            "(computed_tier IS NOT NULL AND computed_tier = final_tier)))",
            name="kyc_assessment_audit_reason_when_overridden",
        ),
        Index(
            "idx_kyc_assessment_audit_application_recorded_at",
            "application_id",
            "recorded_at",
        ),
    )

    audit_id: Mapped[uuid.UUID] = mapped_column(
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
    computed_risk_rating: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("kyc_risk_ratings.rating", ondelete="RESTRICT"),
        nullable=True,
    )
    final_risk_rating: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("kyc_risk_ratings.rating", ondelete="RESTRICT"),
        nullable=True,
    )
    risk_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    computed_tier: Mapped[int | None] = mapped_column(
        SmallInteger,
        ForeignKey("kyc_tiers.tier", ondelete="RESTRICT"),
        nullable=True,
    )
    final_tier: Mapped[int | None] = mapped_column(
        SmallInteger,
        ForeignKey("kyc_tiers.tier", ondelete="RESTRICT"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NULL for a submission, which the applicant makes rather than a reviewer.
    # RESTRICT for the same reason as `kyc_decisions.decided_by_user_id`.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
