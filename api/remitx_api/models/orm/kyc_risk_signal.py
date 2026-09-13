"""The risk signals an application is scored on, and what each one is worth.

Everything that is a judgement call is a column here, so compliance can reweight
or switch off a signal without a release:

- `score_effect` — points added to the 0-100 risk score when the signal fires
- `is_active` — an inactive signal is never evaluated and adds nothing

What a signal *detects* is code — a detector in services/kyc_risk_rules.py,
keyed by `signal`. Loading the rule set refuses an active row with no detector,
so a signal cannot silently score nothing.

Seeded from models/orm/kyc_seed.py.
"""

from sqlalchemy import Boolean, CheckConstraint, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base
from remitx_api.models.orm.kyc_lifecycle import MAX_RISK_SCORE, MIN_RISK_SCORE


class KycRiskSignalRecord(Base):
    __tablename__ = "kyc_risk_signals"
    __table_args__ = (
        CheckConstraint(
            f"score_effect >= {MIN_RISK_SCORE} AND score_effect <= {MAX_RISK_SCORE}",
            name="kyc_risk_signals_score_effect_in_range",
        ),
    )

    signal: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    score_effect: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
