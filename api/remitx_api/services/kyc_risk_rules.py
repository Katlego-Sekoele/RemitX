"""KYC risk rating and risk-based limits: every rule, in one module, as pure
functions.

An application is scored 0-100 at submission and the score's band is its risk
rating. With the rule set the migrations seed (models/orm/kyc_seed.py):

    Signal                                 Fires when                   Effect
    ─────────────────────────────────────  ───────────────────────────  ──────
    pep_declared                           any PEP declaration              60
    foreign_jurisdiction                   non-ZA nationality, or           25
                                           address outside ZA
    expected_volume_above_standard_limit   expected monthly volume          25
                                           above the tier 1 monthly
                                           limit
    source_of_funds_other                  source of funds `other`          25
                                           with free text
    non_sa_identity_document               ID document not a SA ID          25

    Rating   Score     Max tier  Limits  Next review  Officer must decide
    ───────  ────────  ────────  ──────  ───────────  ───────────────────
    low       0 – 24   2         100%    730 days     no (unless PEP)
    medium   25 – 59   2          75%    365 days     no (unless PEP)
    high     60 – 100  1          50%    180 days     yes

So any one signal on its own reaches at least `medium`, a PEP declaration on
its own reaches `high`, no signals is `low` — and, deliberately, signals
accumulate: three independent `medium` signals score 75 and land in `high`.

A customer's limits are their tier's limits scaled by their rating's
`limit_percent` (`allowance_for`). Risk only ever lowers a limit, so nothing
here can take a customer past the brief's figures for their tier.

**What is data and what is code.** Every number above is a row, and none of
it is read from this docstring or from the seed module at runtime: signal
weights and on/off in `kyc_risk_signals`; band boundaries and consequences in
`kyc_risk_ratings`; tier limits in `kyc_tiers`. Compliance changes any of them
with an UPDATE, and the functions below take them as a `RiskRuleSet`. What a
signal *detects* is code — `SIGNAL_DETECTORS`, keyed by the signal's row —
because a detector is logic, not a number. A new kind of signal is a detector
here plus a migration seeding its row; `RiskRuleSet` refuses an active row with
no detector rather than letting it silently score nothing.

**What this is not.** No sanctions list, PEP database or adverse-media
screening happens anywhere. Every input is the applicant's own declaration,
reviewed by a human, and nothing that shows a rating may claim otherwise.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Protocol

from remitx_api.errors.kyc import (
    IncompleteKycDeclarationError,
    KycRiskRulesMisconfiguredError,
    UnknownKycRiskRatingError,
)
from remitx_api.models.orm.kyc_lifecycle import (
    MAX_RISK_SCORE,
    MIN_RISK_SCORE,
    KycIdType,
    KycSourceOfFunds,
)

SOUTH_AFRICA = "ZA"
CENTS = Decimal("0.01")


class DeclaredApplication(Protocol):
    """The declared fields the rules read. `KycApplication` satisfies it; a
    test can pass anything else that does."""

    nationality: str | None
    residential_country: str | None
    id_type: str | None
    issuing_country: str | None
    source_of_funds: str | None
    source_of_funds_detail: str | None
    expected_monthly_volume_zar: Decimal | None
    is_domestic_prominent_influential_person: bool | None
    is_foreign_prominent_public_official: bool | None
    is_pep_family_or_close_associate: bool | None
    pep_relationship: str | None
    pep_position: str | None
    pep_country: str | None
    source_of_wealth: str | None


@dataclass(frozen=True, slots=True)
class RiskFacts:
    """What the applicant declared, reduced to what the detectors look at."""

    nationality: str | None = None
    residential_country: str | None = None
    id_type: str | None = None
    issuing_country: str | None = None
    source_of_funds: str | None = None
    expected_monthly_volume_zar: Decimal | None = None
    declares_pep: bool = False

    @classmethod
    def from_application(cls, application: DeclaredApplication) -> RiskFacts:
        return cls(
            nationality=application.nationality,
            residential_country=application.residential_country,
            id_type=application.id_type,
            issuing_country=application.issuing_country,
            source_of_funds=application.source_of_funds,
            expected_monthly_volume_zar=application.expected_monthly_volume_zar,
            declares_pep=declares_pep(application),
        )


@dataclass(frozen=True, slots=True)
class RiskBand:
    """One `kyc_risk_ratings` row."""

    rating: str
    min_score: int
    max_score: int
    severity: int
    max_tier: int
    limit_percent: int
    review_interval_days: int
    requires_senior_approval: bool

    def contains(self, score: int) -> bool:
        return self.min_score <= score <= self.max_score


@dataclass(frozen=True, slots=True)
class TierLimits:
    """One `kyc_tiers` row, as far as limits are concerned."""

    tier: int
    daily_limit_zar: Decimal
    monthly_limit_zar: Decimal


@dataclass(frozen=True, slots=True)
class RiskRuleSet:
    """The rule set as the database holds it right now.

    `signal_effects` holds *active* signals only — an inactive signal is not
    evaluated at all, rather than evaluated and worth nothing, so it never
    appears among an application's matched signals.

    Construction refuses a rule set that cannot be scored against: bands that
    leave a score unrated or rate one twice, or an active signal with no
    detector. The database cannot enforce either — each CHECK sees one row —
    and a broken rule set should fail loudly, not mis-rate an application.
    """

    signal_effects: Mapping[str, int]
    bands: tuple[RiskBand, ...]
    standard_monthly_limit_zar: Decimal

    def __post_init__(self) -> None:
        ratings = [band.rating for band in self.bands]
        if not ratings or len(ratings) != len(set(ratings)):
            raise KycRiskRulesMisconfiguredError(
                "kyc_risk_ratings must hold at least one band, each rating once"
            )

        expected_min = MIN_RISK_SCORE
        for band in sorted(self.bands, key=lambda band: band.min_score):
            if band.min_score != expected_min:
                raise KycRiskRulesMisconfiguredError(
                    "kyc_risk_ratings bands must be contiguous: expected a band "
                    f"starting at {expected_min}, found {band.rating!r} starting "
                    f"at {band.min_score}"
                )
            expected_min = band.max_score + 1
        if expected_min != MAX_RISK_SCORE + 1:
            raise KycRiskRulesMisconfiguredError(
                f"kyc_risk_ratings bands must reach {MAX_RISK_SCORE}; the highest "
                f"ends at {expected_min - 1}"
            )

        undetectable = sorted(set(self.signal_effects) - set(SIGNAL_DETECTORS))
        if undetectable:
            raise KycRiskRulesMisconfiguredError(
                "Active kyc_risk_signals rows have no detector in "
                f"services/kyc_risk_rules.py: {', '.join(undetectable)}"
            )

    def band_for_score(self, score: int) -> RiskBand:
        # Always found: __post_init__ proved the bands cover the whole range.
        return next(band for band in self.bands if band.contains(score))

    def band_for_rating(self, rating: str) -> RiskBand:
        for band in self.bands:
            if band.rating == rating:
                return band
        raise UnknownKycRiskRatingError(rating)


@dataclass(frozen=True, slots=True)
class MatchedSignal:
    """A signal that fired, with the score effect it carried *at the time*."""

    signal: str
    score_effect: int


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    score: int
    rating: str
    matched_signals: tuple[MatchedSignal, ...]


@dataclass(frozen=True, slots=True)
class Allowance:
    """What a customer may actually send: their tier's limits, scaled by risk."""

    tier: int
    limit_percent: int
    daily_limit_zar: Decimal
    monthly_limit_zar: Decimal


# --- Detectors ----------------------------------------------------------------
#
# One per signal, keyed by `kyc_risk_signals.signal`. Each answers "did the
# applicant declare this?" — an undeclared field fires nothing, because
# completeness is the submission check's job, not the scorer's.


def _is_outside_south_africa(country: str | None) -> bool:
    return country is not None and country.strip().upper() != SOUTH_AFRICA


def _detect_pep_declared(facts: RiskFacts, _rules: RiskRuleSet) -> bool:
    return facts.declares_pep


def _detect_foreign_jurisdiction(facts: RiskFacts, _rules: RiskRuleSet) -> bool:
    return _is_outside_south_africa(facts.nationality) or _is_outside_south_africa(
        facts.residential_country
    )


def _detect_expected_volume_above_standard_limit(
    facts: RiskFacts, rules: RiskRuleSet
) -> bool:
    return (
        facts.expected_monthly_volume_zar is not None
        and facts.expected_monthly_volume_zar > rules.standard_monthly_limit_zar
    )


def _detect_source_of_funds_other(facts: RiskFacts, _rules: RiskRuleSet) -> bool:
    return facts.source_of_funds == KycSourceOfFunds.OTHER.value


def _detect_non_sa_identity_document(facts: RiskFacts, _rules: RiskRuleSet) -> bool:
    # A national ID issued by another country is not a SA ID either.
    if facts.id_type is None:
        return False
    return facts.id_type != KycIdType.NATIONAL_ID.value or _is_outside_south_africa(
        facts.issuing_country
    )


SIGNAL_DETECTORS: dict[str, Callable[[RiskFacts, RiskRuleSet], bool]] = {
    "pep_declared": _detect_pep_declared,
    "foreign_jurisdiction": _detect_foreign_jurisdiction,
    "expected_volume_above_standard_limit": (
        _detect_expected_volume_above_standard_limit
    ),
    "source_of_funds_other": _detect_source_of_funds_other,
    "non_sa_identity_document": _detect_non_sa_identity_document,
}


# --- Scoring ------------------------------------------------------------------


def assess_risk(facts: RiskFacts, rules: RiskRuleSet) -> RiskAssessment:
    """Score an application against a rule set. Pure: same inputs, same answer.

    Sum the score effect of every active signal that fires, clamp to 0-100,
    and rate the score by the band it falls in. Matched signals come back in
    detector order, so the same application always lists them the same way.
    """
    matched = tuple(
        MatchedSignal(signal, rules.signal_effects[signal])
        for signal, detect in SIGNAL_DETECTORS.items()
        if signal in rules.signal_effects and detect(facts, rules)
    )
    score = max(
        MIN_RISK_SCORE,
        min(MAX_RISK_SCORE, sum(match.score_effect for match in matched)),
    )
    return RiskAssessment(
        score=score,
        rating=rules.band_for_score(score).rating,
        matched_signals=matched,
    )


# --- Risk-based limits ----------------------------------------------------------


def allowance_for(tier: TierLimits, band: RiskBand | None) -> Allowance:
    """A customer's limits: the tier's, scaled down by the rating's
    `limit_percent`. Rounded down to the cent, so scaling never grants a
    fraction more than the percentage says.

    `band` is None only for a customer approved without ever being assessed;
    they get the tier's limits unscaled, as they would have before risk-based
    limits existed.
    """
    percent = 100 if band is None else band.limit_percent

    def scale(limit: Decimal) -> Decimal:
        return (limit * percent / 100).quantize(CENTS, rounding=ROUND_DOWN)

    return Allowance(
        tier=tier.tier,
        limit_percent=percent,
        daily_limit_zar=scale(tier.daily_limit_zar),
        monthly_limit_zar=scale(tier.monthly_limit_zar),
    )


# --- Enhanced due diligence at submission ---------------------------------------


def declares_pep(application: DeclaredApplication) -> bool:
    return any(
        (
            application.is_domestic_prominent_influential_person,
            application.is_foreign_prominent_public_official,
            application.is_pep_family_or_close_associate,
        )
    )


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def missing_risk_declarations(application: DeclaredApplication) -> list[str]:
    """Fields the risk rules need before this application can be submitted.

    Not the full completeness check — that belongs to the submit ticket — only
    what a declaration this module scores makes mandatory:

    - a yes to any PEP question requires the relationship, position and
      country, and a source of wealth (enhanced due diligence);
    - source of funds `other` requires the free text that says what it is.
    """
    missing: list[str] = []
    if declares_pep(application):
        for field in (
            "pep_relationship",
            "pep_position",
            "pep_country",
            "source_of_wealth",
        ):
            if _is_blank(getattr(application, field)):
                missing.append(field)
    if application.source_of_funds == KycSourceOfFunds.OTHER.value and _is_blank(
        application.source_of_funds_detail
    ):
        missing.append("source_of_funds_detail")
    return missing


def require_risk_declarations(application: DeclaredApplication) -> None:
    missing = missing_risk_declarations(application)
    if missing:
        raise IncompleteKycDeclarationError(missing)
