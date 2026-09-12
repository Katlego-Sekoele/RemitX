"""The KYC lifecycle: one status vocabulary, one table of legal moves.

`kyc_applications.status` is the only stored copy. A *user's* KYC standing is
derived from their applications on read — `KycApplicationRepository.get_standing`
— rather than denormalised onto `users`, so there is no second copy to disagree
with the first.

The machine:

    not_started ─→ in_progress ─→ submitted ─→ under_review ─┬─→ approved ─→ review_due
                        ↑                                    ├─→ rejected
                        └──────── more_info_required ←───────┘

`not_started` is the derived answer for a user with no application row at all.
An application is born `in_progress`, so no row ever holds that value, and
`APPLICATION_STATUSES` — the set the CHECK constraint is built from — excludes
it.

**Resubmission is a new row, not a transition.** Neither `rejected` nor
`review_due` has an outgoing edge here. A rejected attempt keeps the data it
was rejected on — overwriting it would make "what did they claim the first
time, and why did we reject it?" unanswerable, which is the opposite of what
FICA §23 record-keeping asks for. `KycController.start_application` is the only
way out of both states, and the new row it inserts is what moves the user's
derived status back to `in_progress`.

`more_info_required` is the exception, and deliberately so: a blurry photo
should not cost the applicant their whole attempt, so that edge returns to
`in_progress` *on the same row*.

`review_due` exists for FICA §21C ongoing due diligence. Nothing schedules it
— no periodic-refresh worker is in scope — but the state and
`kyc_applications.next_review_at` are what let the technical specification
describe how refresh would work, at the cost of one column.
"""

from enum import StrEnum

# Ongoing due diligence (FICA §21C): how far ahead of an approval the next
# refresh falls due. One year is a placeholder for a risk-based schedule —
# a high-risk applicant would be reviewed more often than this.
REVIEW_INTERVAL_DAYS = 365

# `kyc_applications.tier_granted`, surfaced as `KycStanding.tier`. The brief's
# limit table has two rows — Unverified ZAR 0/0, Verified ZAR 3,000/25,000 — so
# two tiers is the whole ladder today. Enforcement of the numbers belongs to the
# limits ticket, not here; this is only the number it will key off.
KYC_TIER_NONE = 0
KYC_TIER_VERIFIED = 1


class KycStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    MORE_INFO_REQUIRED = "more_info_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVIEW_DUE = "review_due"


# The machine, as data. `KycController.transition` is the only reader, and
# anything absent from a status's set raises rather than silently no-opping.
LEGAL_TRANSITIONS: dict[KycStatus, frozenset[KycStatus]] = {
    KycStatus.NOT_STARTED: frozenset(),
    KycStatus.IN_PROGRESS: frozenset({KycStatus.SUBMITTED}),
    KycStatus.SUBMITTED: frozenset({KycStatus.UNDER_REVIEW}),
    KycStatus.UNDER_REVIEW: frozenset(
        {
            KycStatus.APPROVED,
            KycStatus.REJECTED,
            KycStatus.MORE_INFO_REQUIRED,
        }
    ),
    KycStatus.MORE_INFO_REQUIRED: frozenset({KycStatus.IN_PROGRESS}),
    KycStatus.APPROVED: frozenset({KycStatus.REVIEW_DUE}),
    KycStatus.REJECTED: frozenset(),
    KycStatus.REVIEW_DUE: frozenset(),
}

# An application still on its way to an outcome. The partial unique index on
# `kyc_applications.user_id` covers exactly this set, so a user can hold at
# most one at a time. `review_due` is deliberately *not* open: a refresh has
# to be able to open a new application while the approved one still stands.
OPEN_STATUSES = frozenset(
    {
        KycStatus.IN_PROGRESS,
        KycStatus.SUBMITTED,
        KycStatus.UNDER_REVIEW,
        KycStatus.MORE_INFO_REQUIRED,
    }
)

# Transitions a reviewer makes, and therefore the ones that append a
# `kyc_decisions` row naming who made them. `submitted` and `in_progress` are
# applicant actions with no decision to record; `review_due` is a clock.
# Claiming an application (`under_review`) counts: knowing which reviewer
# picked it up is what stops two of them working it in parallel.
DECISION_STATUSES = frozenset(
    {
        KycStatus.UNDER_REVIEW,
        KycStatus.MORE_INFO_REQUIRED,
        KycStatus.APPROVED,
        KycStatus.REJECTED,
    }
)

# `not_started` describes a user with no application, so no row can hold it.
APPLICATION_STATUSES = tuple(
    status for status in KycStatus if status is not KycStatus.NOT_STARTED
)

# A completed verification that still stands. `review_due` is in here on
# purpose: due for refresh is not the same as no longer verified, and dropping
# someone's allowance the moment a review falls due would punish them for the
# platform's scheduling.
VERIFIED_STATUSES = frozenset({KycStatus.APPROVED, KycStatus.REVIEW_DUE})


class KycIdType(StrEnum):
    NATIONAL_ID = "national_id"
    PASSPORT = "passport"


class KycSourceOfFunds(StrEnum):
    """The brief's "source of funds" field, as a closed set rather than free
    text: a reviewer comparing applications needs values that group."""

    SALARY = "salary"
    BUSINESS_INCOME = "business_income"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    GIFT = "gift"
    PENSION = "pension"
    OTHER = "other"


class KycRiskRating(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class KycDocumentType(StrEnum):
    ID_DOCUMENT = "id_document"
    PROOF_OF_ADDRESS = "proof_of_address"
    SELFIE = "selfie"
    SOURCE_OF_FUNDS = "source_of_funds"


class KycReasonCode(StrEnum):
    """Why a reviewer decided what they did.

    A code as well as free text because the free text is for the applicant and
    the code is for reporting — "how many applications failed on document
    legibility this quarter" is not a question you answer by grepping prose.
    """

    IDENTITY_VERIFIED = "identity_verified"
    DOCUMENT_ILLEGIBLE = "document_illegible"
    DOCUMENT_EXPIRED = "document_expired"
    DOCUMENT_MISSING = "document_missing"
    DETAILS_MISMATCH = "details_mismatch"
    SANCTIONS_MATCH = "sanctions_match"
    SUSPECTED_FRAUD = "suspected_fraud"
    UNSUPPORTED_JURISDICTION = "unsupported_jurisdiction"
    UNDER_AGE = "under_age"
    OTHER = "other"


KYC_APPLICATION_STATUS_DESCRIPTIONS: dict[KycStatus, str] = {
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

KYC_REASON_CODE_DESCRIPTIONS: dict["KycReasonCode", str] = {
    KycReasonCode.IDENTITY_VERIFIED: "Identity verified against supplied documents.",
    KycReasonCode.DOCUMENT_ILLEGIBLE: "Submitted document is illegible or unreadable.",
    KycReasonCode.DOCUMENT_EXPIRED: "Submitted document has expired.",
    KycReasonCode.DOCUMENT_MISSING: "Required document was not supplied.",
    KycReasonCode.DETAILS_MISMATCH: "Declared details do not match the documents.",
    KycReasonCode.SANCTIONS_MATCH: "Applicant matched a sanctions screening list.",
    KycReasonCode.SUSPECTED_FRAUD: "Application flagged for suspected fraud.",
    KycReasonCode.UNSUPPORTED_JURISDICTION: "Applicant jurisdiction is not supported.",
    KycReasonCode.UNDER_AGE: "Applicant is below the minimum age.",
    KycReasonCode.OTHER: "Other reason — see free-text explanation.",
}


def sql_value_list(values) -> str:
    """Render an iterable of enum members as a SQL `IN (...)` body.

    The CHECK constraints are built from the enums rather than typed out, so
    adding a member cannot leave the database accepting a narrower set than
    Python does — `permissions_permission_valid` does the same thing in
    models/orm/permission.py.

    Always emitted in enum declaration order, including for the frozensets
    above. Set iteration order for strings varies between interpreter runs
    (hash randomisation), which would make the generated DDL text differ run to
    run — and a partial index whose predicate text keeps changing is drift
    `alembic check` would report, or worse, miss inconsistently.
    """
    members = list(values)
    if not members:
        raise ValueError("A SQL IN (...) list cannot be empty")
    declaration_order = {member: index for index, member in enumerate(type(members[0]))}
    ordered = sorted(members, key=declaration_order.__getitem__)
    return ", ".join(f"'{member.value}'" for member in ordered)
