"""The verification tier ladder and the limits each tier carries.

Configuration, not constants: the limits enforcement path reads a customer's
`tier_granted`, then the limits from this row, so changing a limit is an
update here rather than a release. `kyc_applications.tier_granted` references
`tier`, so an approval cannot grant a tier this table does not define.

Seeded from models/orm/kyc_seed.py.
"""

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Numeric, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class KycTier(Base):
    __tablename__ = "kyc_tiers"
    __table_args__ = (
        CheckConstraint("tier >= 0", name="kyc_tiers_tier_non_negative"),
        CheckConstraint(
            "daily_limit_zar >= 0 AND monthly_limit_zar >= daily_limit_zar",
            name="kyc_tiers_limits_valid",
        ),
    )

    tier: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        autoincrement=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    daily_limit_zar: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    monthly_limit_zar: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Enhanced due diligence asks where the customer's wealth came from, not
    # only where this money came from. Approval to a tier with this set refuses
    # an application that has no source of wealth declared.
    requires_source_of_wealth: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
