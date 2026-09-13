"""Reads the risk rule set and tier ladder out of the database.

The only bridge between the rule rows and services/kyc_risk_rules.py: rows in,
plain rule-set values out, so the rules module stays a pure function of what
it is handed and never touches a session.
"""

from sqlalchemy import select

from remitx_api.errors.kyc import (
    KycRiskRulesMisconfiguredError,
    UnknownKycRiskRatingError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED
from remitx_api.models.orm.kyc_pep_relationship import KycPepRelationshipRecord
from remitx_api.models.orm.kyc_risk_rating import KycRiskRatingRecord
from remitx_api.models.orm.kyc_risk_signal import KycRiskSignalRecord
from remitx_api.models.orm.kyc_tier import KycTier
from remitx_api.services.kyc_risk_rules import (
    RiskBand,
    RiskRuleSet,
    TierLimits,
)


def band_from_record(record: KycRiskRatingRecord) -> RiskBand:
    return RiskBand(
        rating=record.rating,
        min_score=record.min_score,
        max_score=record.max_score,
        severity=record.severity,
        max_tier=record.max_tier,
        limit_percent=record.limit_percent,
        review_interval_days=record.review_interval_days,
        requires_senior_approval=record.requires_senior_approval,
    )


def limits_from_tier(tier: KycTier) -> TierLimits:
    return TierLimits(
        tier=tier.tier,
        daily_limit_zar=tier.daily_limit_zar,
        monthly_limit_zar=tier.monthly_limit_zar,
    )


class KycRiskRuleRepository:
    def list_signals(self) -> list[KycRiskSignalRecord]:
        return list(
            db.session.scalars(
                select(KycRiskSignalRecord).order_by(
                    KycRiskSignalRecord.score_effect.desc(),
                    KycRiskSignalRecord.signal,
                )
            ).all()
        )

    def list_ratings(self) -> list[KycRiskRatingRecord]:
        return list(
            db.session.scalars(
                select(KycRiskRatingRecord).order_by(KycRiskRatingRecord.min_score)
            ).all()
        )

    def list_tiers(self) -> list[KycTier]:
        return list(db.session.scalars(select(KycTier).order_by(KycTier.tier)).all())

    def list_pep_relationships(self) -> list[KycPepRelationshipRecord]:
        return list(
            db.session.scalars(
                select(KycPepRelationshipRecord).order_by(
                    KycPepRelationshipRecord.relationship
                )
            ).all()
        )

    def require_rating(self, rating: str) -> KycRiskRatingRecord:
        record = db.session.get(KycRiskRatingRecord, rating)
        if record is None:
            raise UnknownKycRiskRatingError(rating)
        return record

    def get_tier(self, tier: int) -> KycTier | None:
        return db.session.get(KycTier, tier)

    def load_rule_set(self) -> RiskRuleSet:
        standard_tier = self.get_tier(KYC_TIER_VERIFIED)
        if standard_tier is None:
            raise KycRiskRulesMisconfiguredError(
                f"kyc_tiers has no tier {KYC_TIER_VERIFIED}, which the expected "
                "volume signal compares against"
            )
        return RiskRuleSet(
            signal_effects={
                record.signal: record.score_effect
                for record in self.list_signals()
                if record.is_active
            },
            bands=tuple(band_from_record(record) for record in self.list_ratings()),
            standard_monthly_limit_zar=standard_tier.monthly_limit_zar,
        )
