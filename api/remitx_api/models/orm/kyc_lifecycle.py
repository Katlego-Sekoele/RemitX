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

from datetime import UTC, datetime
from enum import StrEnum

# Ongoing due diligence (FICA §21C): how far ahead of an approval the next
# refresh falls due. The schedule is risk-based — the interval comes from the
# application's `kyc_risk_ratings` row, so a high-risk customer is re-reviewed
# sooner. This constant is only the fallback for an application approved
# without ever being assessed, which submission makes impossible for anything
# that went through `KycController.transition`.
REVIEW_INTERVAL_DAYS = 365

# `kyc_applications.tier_granted`, surfaced as `KycStanding.tier`. The two
# numbers code has to branch on — no approval, and what an approval grants
# unless an officer decides otherwise. Everything else about a tier (its name,
# its limits, whether it needs a source of wealth) and every other tier lives
# in `kyc_tiers`, so the ladder and its limits change without a release.
KYC_TIER_NONE = 0
KYC_TIER_VERIFIED = 1

# The risk score scale. Scores are clamped to it, and the `kyc_risk_ratings`
# bands must cover every score in it — see services/kyc_risk_rules.py.
MIN_RISK_SCORE = 0
MAX_RISK_SCORE = 100


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

# A new application may be opened from these standings and no others: the user
# is still onboarding, or their verification has expired. An approval in force
# blocks it, so an approved customer cannot open a draft by accident.
STARTABLE_STANDINGS = frozenset(
    {KycStatus.NOT_STARTED, KycStatus.REJECTED, KycStatus.REVIEW_DUE}
)


def effective_status(
    status: str, next_review_at: datetime | None, now: datetime
) -> KycStatus:
    """The status to report: an approval past its `next_review_at` is
    `review_due`.

    Derived on read rather than written by a scheduler, so expiry lands on the
    exact instant with nothing to run. The stored row keeps `approved`; every
    reader that reports status goes through here so admin and applicant agree.
    """
    if (
        status == KycStatus.APPROVED.value
        and next_review_at is not None
        # SQLite hands back naive datetimes; every stored timestamp is UTC.
        and (
            next_review_at
            if next_review_at.tzinfo is not None
            else next_review_at.replace(tzinfo=UTC)
        )
        <= now
    ):
        return KycStatus.REVIEW_DUE
    return KycStatus(status)


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


class KycDocumentType(StrEnum):
    ID_DOCUMENT = "id_document"
    PROOF_OF_ADDRESS = "proof_of_address"
    SELFIE = "selfie"
    SOURCE_OF_FUNDS = "source_of_funds"


class KycDocumentStatus(StrEnum):
    """Where an upload has got to.

    A document exists as a row before it exists as bytes: `POST /kyc/documents`
    writes `pending` and hands back a signed upload URL, and only the
    completion call - which checks the object's real size and sniffs its real
    content type - promotes it to `stored`.

    Two states rather than one because the gap between them is where every
    interesting failure lives. A browser that closes mid-upload, a client that
    declared a 40 KB PNG and PUT something else, a signature that expired
    before the file finished: all of them leave `pending`, which no retrieval
    path will serve and no reviewer will ever see.
    """

    PENDING = "pending"
    STORED = "stored"


DOCUMENT_STATUSES = tuple(KycDocumentStatus)


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


# Applicant-facing copy for a decision. The reviewer's free text stays
# internal — FICA tipping-off (§29) forbids telling an applicant they were
# flagged for fraud or a sanctions hit, and a reviewer's note is not a
# customer-safe explanation of the other codes either.
GENERIC_REFUSAL_MESSAGE = (
    "We could not verify this application. You may start a new one."
)
TIPPING_OFF_REASON_CODES = frozenset(
    {KycReasonCode.SUSPECTED_FRAUD, KycReasonCode.SANCTIONS_MATCH}
)
APPLICANT_REASON_MESSAGES: dict[KycReasonCode, str] = {
    KycReasonCode.IDENTITY_VERIFIED: "Your identity has been verified.",
    KycReasonCode.DOCUMENT_ILLEGIBLE: (
        "A submitted document was not clear enough to read."
    ),
    KycReasonCode.DOCUMENT_EXPIRED: "A submitted document has expired.",
    KycReasonCode.DOCUMENT_MISSING: "A required document was missing.",
    KycReasonCode.DETAILS_MISMATCH: (
        "The details you declared do not match your documents."
    ),
    KycReasonCode.SANCTIONS_MATCH: GENERIC_REFUSAL_MESSAGE,
    KycReasonCode.SUSPECTED_FRAUD: GENERIC_REFUSAL_MESSAGE,
    KycReasonCode.UNSUPPORTED_JURISDICTION: (
        "We don't operate in your country of residence."
    ),
    KycReasonCode.UNDER_AGE: "You must be 18 or older to use RemitX.",
    KycReasonCode.OTHER: "We could not approve this application.",
}


def applicant_message_for(reason_code: str | None) -> str | None:
    """What an applicant may be told about a rejection. Never the internal
    note, and never a tipping-off reason."""
    if reason_code is None:
        return None
    try:
        code = KycReasonCode(reason_code)
    except ValueError:
        return GENERIC_REFUSAL_MESSAGE
    if code in TIPPING_OFF_REASON_CODES:
        return GENERIC_REFUSAL_MESSAGE
    return APPLICANT_REASON_MESSAGES[code]


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
