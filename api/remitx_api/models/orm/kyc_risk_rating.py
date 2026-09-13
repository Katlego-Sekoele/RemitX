"""Risk rating bands: which scores are low, medium and high, and what a rating
means for the customer.

Nothing in code branches on a rating's name. Every consequence of a rating is a
column on its row, tunable without a release:

- `min_score` / `max_score` — the inclusive score band. Bands must cover 0-100
  with no gap or overlap; the rules module refuses to score against a set that
  does not (a CHECK constraint cannot see other rows).
- `severity` — queue ordering, highest first.
- `max_tier` — the highest tier an approval at this rating may grant. At least
  1 by constraint: a rating may route a decision to an officer, never make
  approval impossible.
- `limit_percent` — the share of the tier's daily and monthly limits the
  customer actually gets. Risk can only lower a limit, never raise one past
  the tier's, so nothing about the rating can exceed the brief's figures.
- `review_interval_days` — how soon the next ongoing-due-diligence review
  falls due after approval (FICA §21C).
- `requires_senior_approval` — approving or rejecting needs
  `kyc:application:decide`, whatever else the actor holds.

Seeded from models/orm/kyc_seed.py.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base
from remitx_api.models.orm.kyc_lifecycle import (
    KYC_TIER_VERIFIED,
    MAX_RISK_SCORE,
    MIN_RISK_SCORE,
)


class KycRiskRatingRecord(Base):
    __tablename__ = "kyc_risk_ratings"
    __table_args__ = (
        CheckConstraint(
            f"min_score >= {MIN_RISK_SCORE} AND max_score <= {MAX_RISK_SCORE} "
            "AND min_score <= max_score",
            name="kyc_risk_ratings_score_band_valid",
        ),
        CheckConstraint(
            f"max_tier >= {KYC_TIER_VERIFIED}",
            name="kyc_risk_ratings_max_tier_allows_approval",
        ),
        CheckConstraint(
            "limit_percent > 0 AND limit_percent <= 100",
            name="kyc_risk_ratings_limit_percent_valid",
        ),
        CheckConstraint(
            "review_interval_days > 0",
            name="kyc_risk_ratings_review_interval_positive",
        ),
    )

    rating: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    min_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False, unique=True)
    max_tier: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("kyc_tiers.tier", ondelete="RESTRICT"),
        nullable=False,
    )
    limit_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    review_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_senior_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
