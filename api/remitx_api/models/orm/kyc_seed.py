"""Baseline KYC reference data: what the migrations insert, and what tests load
into their throwaway databases. Nothing else reads this module.

The database is the authority for every row here. Once migrated, a description,
a signal's score effect, a band boundary or a tier's limit is changed with an
UPDATE, and the API reads the row — never these tuples — when it scores an
application, grants a tier, or shows a reviewer what a code means.

Statuses, reason codes and progressions are keyed by the Python enums because
code branches on those values. The risk vocabulary (signals, ratings, PEP
relationships) is keyed by plain strings because nothing branches on it: a
rating's consequences are columns on its row, not `if rating == "high"`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from remitx_api.models.orm.kyc_lifecycle import (
    APPLICATION_STATUSES,
    KYC_TIER_NONE,
    KYC_TIER_VERIFIED,
    LEGAL_TRANSITIONS,
    OPEN_STATUSES,
    KycReasonCode,
    KycStatus,
)

KYC_NAMESPACE = uuid.UUID("8f14e45f-ceea-467a-9a5f-0d2a5c8b4e01")


def precompute_progression_id(from_status: str, to_status: str) -> uuid.UUID:
    return uuid.uuid5(KYC_NAMESPACE, f"progression:{from_status}:{to_status}")


@dataclass(frozen=True, slots=True)
class KycReasonCodeSeed:
    code: KycReasonCode
    description: str


REASON_CODE_SEEDS: tuple[KycReasonCodeSeed, ...] = (
    KycReasonCodeSeed(
        KycReasonCode.IDENTITY_VERIFIED,
        "Identity verified against supplied documents.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.DOCUMENT_ILLEGIBLE,
        "Submitted document is illegible or unreadable.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.DOCUMENT_EXPIRED,
        "Submitted document has expired.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.DOCUMENT_MISSING,
        "Required document was not supplied.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.DETAILS_MISMATCH,
        "Declared details do not match the documents.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.SANCTIONS_MATCH,
        "Applicant matched a sanctions screening list.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.SUSPECTED_FRAUD,
        "Application flagged for suspected fraud.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.UNSUPPORTED_JURISDICTION,
        "Applicant jurisdiction is not supported.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.UNDER_AGE,
        "Applicant is below the minimum age.",
    ),
    KycReasonCodeSeed(
        KycReasonCode.OTHER,
        "Other reason — see free-text explanation.",
    ),
)


@dataclass(frozen=True, slots=True)
class KycStatusProgressionSeed:
    from_status: KycStatus
    to_status: KycStatus


PROGRESSION_SEEDS: tuple[KycStatusProgressionSeed, ...] = tuple(
    KycStatusProgressionSeed(from_status, to_status)
    for from_status, targets in LEGAL_TRANSITIONS.items()
    for to_status in sorted(targets, key=lambda status: status.value)
)


_APPLICATION_STATUS_DESCRIPTIONS: dict[KycStatus, str] = {
    KycStatus.IN_PROGRESS: "Applicant is completing the KYC wizard.",
    KycStatus.SUBMITTED: "Application submitted and awaiting review assignment.",
    KycStatus.UNDER_REVIEW: "A reviewer is actively assessing the application.",
    KycStatus.MORE_INFO_REQUIRED: (
        "Reviewer requested corrected or missing information."
    ),
    KycStatus.APPROVED: "Identity verified and allowance tier granted.",
    KycStatus.REJECTED: "Application rejected; the attempt is preserved for audit.",
    KycStatus.REVIEW_DUE: "Verification stands but periodic refresh is due.",
}


@dataclass(frozen=True, slots=True)
class KycApplicationStatusSeed:
    status: KycStatus
    description: str
    is_open: bool
    is_terminal: bool


APPLICATION_STATUS_SEEDS: tuple[KycApplicationStatusSeed, ...] = tuple(
    KycApplicationStatusSeed(
        status=KycStatus(status),
        description=_APPLICATION_STATUS_DESCRIPTIONS[KycStatus(status)],
        is_open=KycStatus(status) in OPEN_STATUSES,
        is_terminal=len(LEGAL_TRANSITIONS[KycStatus(status)]) == 0,
    )
    for status in APPLICATION_STATUSES
)


# --- Verification tiers --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KycTierSeed:
    tier: int
    name: str
    description: str
    daily_limit_zar: Decimal
    monthly_limit_zar: Decimal
    requires_source_of_wealth: bool


# FICA's simplified / standard / enhanced due diligence mapped onto the brief's
# limits. Tier 1's numbers are the brief's; tier 2's are ours, and exist to show
# the mechanism.
TIER_SEEDS: tuple[KycTierSeed, ...] = (
    KycTierSeed(
        tier=KYC_TIER_NONE,
        name="Unverified",
        description="Default on registration. No approved application.",
        daily_limit_zar=Decimal("0.00"),
        monthly_limit_zar=Decimal("0.00"),
        requires_source_of_wealth=False,
    ),
    KycTierSeed(
        tier=KYC_TIER_VERIFIED,
        name="Standard CDD",
        description="Approved application under standard customer due diligence.",
        daily_limit_zar=Decimal("3000.00"),
        monthly_limit_zar=Decimal("25000.00"),
        requires_source_of_wealth=False,
    ),
    KycTierSeed(
        tier=2,
        name="Enhanced CDD",
        description=(
            "Standard CDD plus a declared source of wealth, granted by a "
            "compliance officer."
        ),
        daily_limit_zar=Decimal("10000.00"),
        monthly_limit_zar=Decimal("100000.00"),
        requires_source_of_wealth=True,
    ),
)


# --- Risk rule set ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KycRiskRatingSeed:
    rating: str
    description: str
    min_score: int
    max_score: int
    severity: int
    max_tier: int
    limit_percent: int
    review_interval_days: int
    requires_senior_approval: bool


# `limit_percent` scales the tier's limits down for riskier customers: a
# medium-risk tier 1 customer gets R2,250 a day and R18,750 a month. Only ever
# down — 100 is the ceiling, so the brief's tier 1 figures are the most anyone
# at tier 1 can get.
RISK_RATING_SEEDS: tuple[KycRiskRatingSeed, ...] = (
    KycRiskRatingSeed(
        rating="low",
        description="No risk signals. Standard due diligence, full tier limits.",
        min_score=0,
        max_score=24,
        severity=1,
        max_tier=2,
        limit_percent=100,
        review_interval_days=730,
        requires_senior_approval=False,
    ),
    KycRiskRatingSeed(
        rating="medium",
        description=(
            "One or two risk signals. Standard due diligence at reduced limits."
        ),
        min_score=25,
        max_score=59,
        severity=2,
        max_tier=2,
        limit_percent=75,
        review_interval_days=365,
        requires_senior_approval=False,
    ),
    # Does not block approval — auto-rejecting on risk alone would be bad
    # compliance practice. It routes the decision to an officer, caps the
    # customer at half of tier 1's limits, and brings the next review forward.
    KycRiskRatingSeed(
        rating="high",
        description=(
            "PEP declaration or several risk signals. Officer decision, tier 1 "
            "at most, half limits, and enhanced monitoring."
        ),
        min_score=60,
        max_score=100,
        severity=3,
        max_tier=KYC_TIER_VERIFIED,
        limit_percent=50,
        review_interval_days=180,
        requires_senior_approval=True,
    ),
)


@dataclass(frozen=True, slots=True)
class KycRiskSignalSeed:
    signal: str
    description: str
    score_effect: int


# Additive, clamped to 0-100. Any one signal on its own reaches at least
# `medium`, and a PEP declaration on its own reaches `high` — the ticket's rule
# table. Unlike that table, signals *accumulate*: three independent medium
# signals together score 75 and land in `high`, because a foreign national
# using a passport who also expects above-limit volume is a different risk from
# any one of those facts.
#
# The rule set as V20260913_1005 first inserted it, which imports this tuple —
# so it is frozen: appending here would re-run as part of that migration and
# collide with the later one that adds the row. Later signals go in their own
# tuple; retired ones are listed in `RETIRED_RISK_SIGNALS`, never deleted,
# because assessments that fired them still reference them.
RISK_SIGNAL_SEEDS: tuple[KycRiskSignalSeed, ...] = (
    KycRiskSignalSeed(
        signal="pep_declared",
        description=(
            "Applicant declared themselves, an immediate family member, or a "
            "known close associate to be a domestic prominent influential person "
            "(FICA §21F) or a foreign prominent public official (§21G)."
        ),
        score_effect=60,
    ),
    KycRiskSignalSeed(
        signal="foreign_jurisdiction",
        description=(
            "Declared nationality is not South African, or declared residential "
            "address is outside South Africa."
        ),
        score_effect=25,
    ),
    KycRiskSignalSeed(
        signal="expected_volume_above_standard_limit",
        description=(
            "Declared expected monthly volume is above the tier 1 (standard CDD) "
            "monthly limit."
        ),
        score_effect=25,
    ),
    KycRiskSignalSeed(
        signal="source_of_funds_other",
        description="Source of funds declared as 'other' and described in free text.",
        score_effect=25,
    ),
    KycRiskSignalSeed(
        signal="non_sa_identity_document",
        description="Identity document is not a South African national ID.",
        score_effect=25,
    ),
)


# ZA-anchored signals, deactivated once RemitX operated in more than one
# country: a US citizen living in the US with an SSN fired both. Replaced
# rather than redefined, so an old assessment that fired `foreign_jurisdiction`
# still means what it meant at the time.
RETIRED_RISK_SIGNALS: frozenset[str] = frozenset(
    {"foreign_jurisdiction", "non_sa_identity_document"}
)

JURISDICTION_RISK_SIGNAL_SEEDS: tuple[KycRiskSignalSeed, ...] = (
    KycRiskSignalSeed(
        signal="nationality_differs_from_residence",
        description=(
            "Declared nationality is not the country of the declared residential "
            "address."
        ),
        score_effect=25,
    ),
    KycRiskSignalSeed(
        signal="non_national_identity_document",
        description=(
            "Identified by passport rather than a national identity number whose "
            "structure can be checked."
        ),
        score_effect=25,
    ),
)

# The rule set as it stands after every migration: what tests score against.
# Every signal here must have a detector in services/kyc_risk_rules.py.
ACTIVE_RISK_SIGNAL_SEEDS: tuple[KycRiskSignalSeed, ...] = tuple(
    seed
    for seed in (*RISK_SIGNAL_SEEDS, *JURISDICTION_RISK_SIGNAL_SEEDS)
    if seed.signal not in RETIRED_RISK_SIGNALS
)


@dataclass(frozen=True, slots=True)
class KycPepRelationshipSeed:
    relationship: str
    description: str


# FICA's vocabulary, so the specification can cite it: §21F and §21G define the
# prominent person, §21H extends both to family members and close associates.
PEP_RELATIONSHIP_SEEDS: tuple[KycPepRelationshipSeed, ...] = (
    KycPepRelationshipSeed(
        "self",
        "The applicant is the prominent person.",
    ),
    KycPepRelationshipSeed(
        "immediate_family_member",
        "An immediate family member of a prominent person (FICA §21H).",
    ),
    KycPepRelationshipSeed(
        "known_close_associate",
        "A known close associate of a prominent person (FICA §21H).",
    ),
)


if {seed.code for seed in REASON_CODE_SEEDS} != set(KycReasonCode):
    raise RuntimeError("REASON_CODE_SEEDS must cover every KycReasonCode member")

if {seed.status.value for seed in APPLICATION_STATUS_SEEDS} != set(
    APPLICATION_STATUSES
):
    raise RuntimeError("APPLICATION_STATUS_SEEDS must cover every application status")


# --- Onboarding wizard --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KycOnboardingStepSeed:
    step: str
    position: int
    role: str
    description: str


ONBOARDING_STEP_SEEDS: tuple[KycOnboardingStepSeed, ...] = (
    KycOnboardingStepSeed(
        "welcome",
        0,
        "entry",
        "What you will need, and that a person reviews the application.",
    ),
    KycOnboardingStepSeed(
        "identity",
        1,
        "collect",
        "Full legal name, date of birth and nationality.",
    ),
    KycOnboardingStepSeed(
        "id-document",
        2,
        "collect",
        "Issuing country, ID type, number, expiry where it applies, and the ID "
        "document.",
    ),
    KycOnboardingStepSeed(
        "address",
        3,
        "collect",
        "Structured residential address and proof of address.",
    ),
    KycOnboardingStepSeed(
        "contact",
        4,
        "collect",
        "Mobile number and contact email.",
    ),
    KycOnboardingStepSeed(
        "financial",
        5,
        "collect",
        "Source of funds, expected volume, and source of wealth when required.",
    ),
    KycOnboardingStepSeed(
        "declarations",
        6,
        "collect",
        "PEP/DPIP/FPPO self-declaration.",
    ),
    KycOnboardingStepSeed(
        "review",
        7,
        "review",
        "Read everything back, then submit.",
    ),
    KycOnboardingStepSeed(
        "status",
        8,
        "outcome",
        "Pending, approved, rejected, or more information required.",
    ),
)


@dataclass(frozen=True, slots=True)
class KycOnboardingRequirementSeed:
    step: str
    name: str
    kind: str
    required_when: str
    copy_on_resubmit: bool


def _fields(
    step: str, *names: str, when: str = "always"
) -> tuple[KycOnboardingRequirementSeed, ...]:
    return tuple(
        KycOnboardingRequirementSeed(step, name, "field", when, True) for name in names
    )


# Frozen for the same reason as `RISK_SIGNAL_SEEDS`: V20260913_1100 imports it.
ONBOARDING_REQUIREMENT_SEEDS: tuple[KycOnboardingRequirementSeed, ...] = (
    *_fields("identity", "full_name", "date_of_birth", "nationality"),
    *_fields("id-document", "id_type", "id_number", "issuing_country"),
    KycOnboardingRequirementSeed(
        "id-document", "id_document", "document", "always", False
    ),
    *_fields(
        "address",
        "residential_line1",
        "residential_city",
        "residential_postal_code",
        "residential_country",
    ),
    KycOnboardingRequirementSeed(
        "address", "residential_line2", "field", "never", True
    ),
    KycOnboardingRequirementSeed(
        "address", "proof_of_address", "document", "always", False
    ),
    *_fields("contact", "mobile_number", "email"),
    *_fields("financial", "source_of_funds", "expected_monthly_volume_zar"),
    KycOnboardingRequirementSeed(
        "financial",
        "source_of_funds_detail",
        "field",
        "source_of_funds_other",
        True,
    ),
    KycOnboardingRequirementSeed(
        "financial", "source_of_wealth", "field", "declares_pep", True
    ),
    *_fields(
        "declarations",
        "is_domestic_prominent_influential_person",
        "is_foreign_prominent_public_official",
        "is_pep_family_or_close_associate",
    ),
    *_fields(
        "declarations",
        "pep_relationship",
        "pep_position",
        "pep_country",
        when="declares_pep",
    ),
    KycOnboardingRequirementSeed("declarations", "pep_details", "field", "never", True),
)


# Added with identity schemes: a passport's expiry date.
ID_EXPIRY_REQUIREMENT_SEEDS: tuple[KycOnboardingRequirementSeed, ...] = (
    KycOnboardingRequirementSeed(
        "id-document", "id_expiry_date", "field", "id_requires_expiry", True
    ),
)


ONBOARDING_EDITABLE_STATUS_SEEDS: tuple[str, ...] = (
    "in_progress",
    "more_info_required",
)


# --- Identity schemes -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KycIdentitySchemeSeed:
    scheme: str
    country: str | None
    id_type: str
    label: str
    validator: str
    requires_expiry: bool
    input_mode: str
    number_hint: str
    document_hint: str


_SCAN_HINT = "PDF, JPEG, PNG or WebP, up to 10 MB. A person will look at this."
_PASSPORT_SCAN_HINT = (
    "The photo page of your passport. PDF, JPEG, PNG or WebP, up to 10 MB."
)

# No any-country `national_id` row, deliberately: a national ID is accepted
# only where a validator knows its structure. Everyone else uses a passport.
IDENTITY_SCHEME_SEEDS: tuple[KycIdentitySchemeSeed, ...] = (
    KycIdentitySchemeSeed(
        scheme="za_national_id",
        country="ZA",
        id_type="national_id",
        label="South African ID",
        validator="za_id",
        requires_expiry=False,
        input_mode="numeric",
        number_hint="13 digits, from your green ID book or smart ID card.",
        document_hint=_SCAN_HINT,
    ),
    KycIdentitySchemeSeed(
        scheme="us_national_id",
        country="US",
        id_type="national_id",
        label="Social Security Number",
        validator="us_ssn",
        requires_expiry=False,
        input_mode="numeric",
        number_hint="9 digits, for example 123-45-6789.",
        # A Social Security card has no photo, so it cannot be the document.
        document_hint=(
            "A government photo ID, such as a driver's licence or state ID. "
            "PDF, JPEG, PNG or WebP, up to 10 MB."
        ),
    ),
    KycIdentitySchemeSeed(
        scheme="za_passport",
        country="ZA",
        id_type="passport",
        label="Passport",
        validator="za_passport",
        requires_expiry=True,
        input_mode="text",
        number_hint="One letter and 8 digits, for example A12345678.",
        document_hint=_PASSPORT_SCAN_HINT,
    ),
    KycIdentitySchemeSeed(
        scheme="us_passport",
        country="US",
        id_type="passport",
        label="Passport",
        validator="us_passport",
        requires_expiry=True,
        input_mode="text",
        number_hint="9 digits, or one letter and 8 digits.",
        document_hint=_PASSPORT_SCAN_HINT,
    ),
    KycIdentitySchemeSeed(
        scheme="passport",
        country=None,
        id_type="passport",
        label="Passport",
        validator="icao_passport",
        requires_expiry=True,
        input_mode="text",
        number_hint="As printed on the photo page, 6 to 9 letters and digits.",
        document_hint=_PASSPORT_SCAN_HINT,
    ),
)
