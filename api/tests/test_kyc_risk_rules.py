"""The risk rules as a pure function: every signal, the combinations, the bands,
and the limits — table-driven, with no database.

The rule set here is built from the seed rows the migration inserts, so these
tests pin the *starting* rule set the specification quotes. The tests at the
bottom prove the function takes its numbers from whatever rule set it is given,
which is what lets compliance tune the rows without a release.
"""

from dataclasses import dataclass, replace
from decimal import Decimal

import pytest
from remitx_api.errors.kyc import (
    IncompleteKycDeclarationError,
    KycRiskRulesMisconfiguredError,
    UnknownKycRiskRatingError,
)
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED
from remitx_api.models.orm.kyc_seed import (
    ACTIVE_RISK_SIGNAL_SEEDS,
    RETIRED_RISK_SIGNALS,
    RISK_RATING_SEEDS,
    TIER_SEEDS,
)
from remitx_api.services.kyc_risk_rules import (
    SIGNAL_DETECTORS,
    RiskBand,
    RiskFacts,
    RiskRuleSet,
    TierLimits,
    allowance_for,
    assess_risk,
    missing_risk_declarations,
    require_risk_declarations,
)

TIER_1 = next(seed for seed in TIER_SEEDS if seed.tier == KYC_TIER_VERIFIED)

SEEDED_BANDS = tuple(
    RiskBand(
        rating=seed.rating,
        min_score=seed.min_score,
        max_score=seed.max_score,
        severity=seed.severity,
        max_tier=seed.max_tier,
        limit_percent=seed.limit_percent,
        review_interval_days=seed.review_interval_days,
        requires_senior_approval=seed.requires_senior_approval,
    )
    for seed in RISK_RATING_SEEDS
)

SEEDED_RULES = RiskRuleSet(
    signal_effects={
        seed.signal: seed.score_effect for seed in ACTIVE_RISK_SIGNAL_SEEDS
    },
    bands=SEEDED_BANDS,
    standard_monthly_limit_zar=TIER_1.monthly_limit_zar,
)

# A South African applicant who trips nothing. Each case changes only the facts
# it is about, so a case failing names exactly one rule.
SA_APPLICANT = RiskFacts(
    nationality="ZA",
    residential_country="ZA",
    id_type="national_id",
    issuing_country="ZA",
    source_of_funds="salary",
    expected_monthly_volume_zar=Decimal("5000.00"),
    declares_pep=False,
)


# --- each rule on its own, and the combinations -----------------------------------

CASES = [
    # (case, changes to SA_APPLICANT, signals that fire, score, rating)
    ("nothing declared", {}, [], 0, "low"),
    ("nothing at all", "empty", [], 0, "low"),
    ("PEP declaration", {"declares_pep": True}, ["pep_declared"], 60, "high"),
    (
        "nationality differs from residence",
        {"nationality": "ZW"},
        ["nationality_differs_from_residence"],
        25,
        "medium",
    ),
    (
        "a US citizen living in the US with an SSN trips nothing",
        {"nationality": "US", "residential_country": "US", "issuing_country": "US"},
        [],
        0,
        "low",
    ),
    (
        "a South African living in the US with an SA ID",
        {"residential_country": "US"},
        ["nationality_differs_from_residence"],
        25,
        "medium",
    ),
    ("country codes compare case-insensitively", {"nationality": "za"}, [], 0, "low"),
    (
        "expected volume above the tier 1 monthly limit",
        {"expected_monthly_volume_zar": Decimal("25000.01")},
        ["expected_volume_above_standard_limit"],
        25,
        "medium",
    ),
    (
        "expected volume exactly at the limit is not above it",
        {"expected_monthly_volume_zar": Decimal("25000.00")},
        [],
        0,
        "low",
    ),
    (
        "source of funds other",
        {"source_of_funds": "other"},
        ["source_of_funds_other"],
        25,
        "medium",
    ),
    (
        "passport",
        {"id_type": "passport"},
        ["non_national_identity_document"],
        25,
        "medium",
    ),
    (
        "a national ID from another country is still a national ID",
        {"issuing_country": "US"},
        [],
        0,
        "low",
    ),
    (
        "foreign national living in ZA with a passport",
        {"nationality": "ZW", "id_type": "passport", "issuing_country": "ZW"},
        ["nationality_differs_from_residence", "non_national_identity_document"],
        50,
        "medium",
    ),
    (
        "three medium signals accumulate into high",
        {
            "nationality": "ZW",
            "id_type": "passport",
            "expected_monthly_volume_zar": Decimal("40000.00"),
        },
        [
            "expected_volume_above_standard_limit",
            "nationality_differs_from_residence",
            "non_national_identity_document",
        ],
        75,
        "high",
    ),
    (
        "every medium signal",
        {
            "nationality": "GB",
            "id_type": "passport",
            "source_of_funds": "other",
            "expected_monthly_volume_zar": Decimal("90000.00"),
        },
        [
            "expected_volume_above_standard_limit",
            "source_of_funds_other",
            "nationality_differs_from_residence",
            "non_national_identity_document",
        ],
        100,
        "high",
    ),
    (
        "everything at once is clamped to 100",
        {
            "declares_pep": True,
            "nationality": "ZW",
            "id_type": "passport",
            "source_of_funds": "other",
            "expected_monthly_volume_zar": Decimal("90000.00"),
        },
        [
            "pep_declared",
            "expected_volume_above_standard_limit",
            "source_of_funds_other",
            "nationality_differs_from_residence",
            "non_national_identity_document",
        ],
        100,
        "high",
    ),
    (
        "PEP plus one medium signal",
        {"declares_pep": True, "source_of_funds": "other"},
        ["pep_declared", "source_of_funds_other"],
        85,
        "high",
    ),
]


@pytest.mark.parametrize(
    ("changes", "signals", "score", "rating"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_the_seeded_rules(changes, signals, score, rating):
    facts = RiskFacts() if changes == "empty" else replace(SA_APPLICANT, **changes)

    assessment = assess_risk(facts, SEEDED_RULES)

    assert [match.signal for match in assessment.matched_signals] == signals
    assert assessment.score == score
    assert assessment.rating == rating


def test_the_ticket_rule_table_holds_for_every_signal_on_its_own():
    """The ticket's table: a PEP declaration alone is `high`, any other signal
    alone is at least `medium`. Checked against every seeded signal, so a
    reweight that broke it would fail here rather than in a demo."""
    for seed in ACTIVE_RISK_SIGNAL_SEEDS:
        band = SEEDED_RULES.band_for_score(seed.score_effect)
        expected = "high" if seed.signal == "pep_declared" else "medium"
        assert band.rating in (expected, "high"), seed.signal
        assert band.rating != "low", seed.signal


def test_every_seeded_signal_has_a_detector_and_every_detector_a_seed():
    assert {seed.signal for seed in ACTIVE_RISK_SIGNAL_SEEDS} == set(SIGNAL_DETECTORS)


def test_retired_signals_are_neither_active_nor_detected():
    """They stay as rows for the assessments that fired them, and nothing
    scores them again."""
    assert RETIRED_RISK_SIGNALS == {"foreign_jurisdiction", "non_sa_identity_document"}
    assert not RETIRED_RISK_SIGNALS & {seed.signal for seed in ACTIVE_RISK_SIGNAL_SEEDS}
    assert not RETIRED_RISK_SIGNALS & set(SIGNAL_DETECTORS)


def test_matched_signals_carry_the_effect_they_scored_with():
    assessment = assess_risk(replace(SA_APPLICANT, declares_pep=True), SEEDED_RULES)

    (match,) = assessment.matched_signals
    assert match.score_effect == 60


# --- the rule set is data -------------------------------------------------------


def test_a_reweighted_signal_changes_the_score():
    rules = replace(
        SEEDED_RULES,
        signal_effects={**SEEDED_RULES.signal_effects, "pep_declared": 30},
    )

    assessment = assess_risk(replace(SA_APPLICANT, declares_pep=True), rules)

    assert assessment.score == 30
    assert assessment.rating == "medium"


def test_an_inactive_signal_is_not_evaluated():
    rules = replace(
        SEEDED_RULES,
        signal_effects={
            signal: effect
            for signal, effect in SEEDED_RULES.signal_effects.items()
            if signal != "nationality_differs_from_residence"
        },
    )

    assessment = assess_risk(replace(SA_APPLICANT, nationality="ZW"), rules)

    assert assessment.matched_signals == ()
    assert assessment.rating == "low"


def test_moved_band_boundaries_change_the_rating():
    low, medium, high = SEEDED_BANDS
    rules = replace(
        SEEDED_RULES,
        bands=(
            replace(low, max_score=29),
            replace(medium, min_score=30),
            high,
        ),
    )

    assessment = assess_risk(replace(SA_APPLICANT, id_type="passport"), rules)

    assert assessment.score == 25
    assert assessment.rating == "low"


def test_the_volume_signal_compares_against_the_tier_limit_it_is_given():
    rules = replace(SEEDED_RULES, standard_monthly_limit_zar=Decimal("50000.00"))

    assessment = assess_risk(
        replace(SA_APPLICANT, expected_monthly_volume_zar=Decimal("40000.00")),
        rules,
    )

    assert assessment.matched_signals == ()


@dataclass
class _BandEdit:
    description: str
    bands: tuple


def _misconfigured_bands():
    low, medium, high = SEEDED_BANDS
    return [
        _BandEdit("gap", (low, replace(medium, min_score=26), high)),
        _BandEdit("overlap", (low, replace(medium, min_score=20), high)),
        _BandEdit("does not start at 0", (replace(low, min_score=1), medium, high)),
        _BandEdit("does not reach 100", (low, medium, replace(high, max_score=99))),
        _BandEdit("duplicate rating", (low, replace(medium, rating="low"), high)),
        _BandEdit("no bands", ()),
    ]


@pytest.mark.parametrize(
    "edit", _misconfigured_bands(), ids=lambda edit: edit.description
)
def test_a_rule_set_that_cannot_rate_every_score_is_refused(edit):
    with pytest.raises(KycRiskRulesMisconfiguredError):
        replace(SEEDED_RULES, bands=edit.bands)


def test_an_active_signal_with_no_detector_is_refused():
    with pytest.raises(KycRiskRulesMisconfiguredError, match="no_such_signal"):
        replace(
            SEEDED_RULES,
            signal_effects={**SEEDED_RULES.signal_effects, "no_such_signal": 10},
        )


def test_an_unknown_rating_is_refused():
    with pytest.raises(UnknownKycRiskRatingError):
        SEEDED_RULES.band_for_rating("extreme")


# --- limits -----------------------------------------------------------------------

TIER_1_LIMITS = TierLimits(
    tier=TIER_1.tier,
    daily_limit_zar=TIER_1.daily_limit_zar,
    monthly_limit_zar=TIER_1.monthly_limit_zar,
)


@pytest.mark.parametrize(
    ("rating", "daily", "monthly"),
    [
        ("low", "3000.00", "25000.00"),
        ("medium", "2250.00", "18750.00"),
        ("high", "1500.00", "12500.00"),
    ],
)
def test_limits_are_the_tier_limits_scaled_by_the_rating(rating, daily, monthly):
    allowance = allowance_for(TIER_1_LIMITS, SEEDED_RULES.band_for_rating(rating))

    assert allowance.daily_limit_zar == Decimal(daily)
    assert allowance.monthly_limit_zar == Decimal(monthly)


def test_no_rating_can_lift_a_limit_past_the_tier():
    for band in SEEDED_BANDS:
        allowance = allowance_for(TIER_1_LIMITS, band)
        assert allowance.daily_limit_zar <= TIER_1.daily_limit_zar
        assert allowance.monthly_limit_zar <= TIER_1.monthly_limit_zar


def test_an_unassessed_customer_gets_the_tier_limits_unscaled():
    allowance = allowance_for(TIER_1_LIMITS, None)

    assert allowance.limit_percent == 100
    assert allowance.daily_limit_zar == TIER_1.daily_limit_zar


def test_scaled_limits_round_down_to_the_cent():
    tier = TierLimits(1, Decimal("100.01"), Decimal("100.01"))
    band = replace(SEEDED_BANDS[0], limit_percent=50)

    assert allowance_for(tier, band).daily_limit_zar == Decimal("50.00")


# --- declarations the rules make mandatory ----------------------------------------


@dataclass
class _Declared:
    nationality: str | None = "ZA"
    residential_country: str | None = "ZA"
    id_type: str | None = "national_id"
    issuing_country: str | None = "ZA"
    source_of_funds: str | None = "salary"
    source_of_funds_detail: str | None = None
    expected_monthly_volume_zar: Decimal | None = None
    is_domestic_prominent_influential_person: bool | None = False
    is_foreign_prominent_public_official: bool | None = False
    is_pep_family_or_close_associate: bool | None = False
    pep_relationship: str | None = None
    pep_position: str | None = None
    pep_country: str | None = None
    source_of_wealth: str | None = None


PEP_DETAILS = {
    "pep_relationship": "self",
    "pep_position": "Deputy Minister",
    "pep_country": "ZA",
    "source_of_wealth": "Salary and an inherited property portfolio.",
}


@pytest.mark.parametrize(
    ("declared", "missing"),
    [
        (_Declared(), []),
        (
            _Declared(is_domestic_prominent_influential_person=True),
            ["pep_relationship", "pep_position", "pep_country", "source_of_wealth"],
        ),
        (
            _Declared(is_foreign_prominent_public_official=True, **PEP_DETAILS),
            [],
        ),
        (
            _Declared(
                is_pep_family_or_close_associate=True,
                **{**PEP_DETAILS, "source_of_wealth": "   "},
            ),
            ["source_of_wealth"],
        ),
        (_Declared(source_of_funds="other"), ["source_of_funds_detail"]),
        (
            _Declared(source_of_funds="other", source_of_funds_detail="Crypto sale"),
            [],
        ),
    ],
    ids=[
        "no PEP, no other",
        "PEP yes needs details and source of wealth",
        "PEP yes with everything",
        "blank source of wealth counts as missing",
        "source of funds other needs its free text",
        "source of funds other with free text",
    ],
)
def test_missing_risk_declarations(declared, missing):
    assert missing_risk_declarations(declared) == missing


def test_require_risk_declarations_names_what_is_missing():
    with pytest.raises(IncompleteKycDeclarationError, match="source_of_wealth"):
        require_risk_declarations(
            _Declared(is_domestic_prominent_influential_person=True)
        )
