"""The signals that fired for one scored `kyc_assessment_audit` row, each with
the score effect it carried *at the time*.

A snapshot, not a reference to the current weight: reweighting
`kyc_risk_signals` later must never rewrite why an old application scored what
it did. The foreign key to the signal still stops a signal that has ever fired
from being deleted — deactivate it (`is_active`) instead.
"""

import uuid

from sqlalchemy import ForeignKey, SmallInteger, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class KycAssessmentAuditSignal(Base):
    __tablename__ = "kyc_assessment_audit_signals"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("kyc_assessment_audit.audit_id", ondelete="CASCADE"),
        primary_key=True,
    )
    signal: Mapped[str] = mapped_column(
        Text,
        ForeignKey("kyc_risk_signals.signal", ondelete="RESTRICT"),
        primary_key=True,
    )
    score_effect: Mapped[int] = mapped_column(SmallInteger, nullable=False)
