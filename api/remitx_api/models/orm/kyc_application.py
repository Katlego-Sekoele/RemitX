"""One KYC attempt, with the PII the applicant declared.

**Why this is not columns on `users`.** A resubmission after rejection would
overwrite the rejected data, and "what did they claim the first time, and why
did we reject it?" then has no answer. FICA §23 runs record-keeping five years
from the end of the business relationship; overwriting is the opposite of that.
So a new attempt is a new row here, and `users` carries only the denormalised
outcome (`kyc_status`, `kyc_tier`, `suspended_at`) that the hot path needs on
every request.

**Every declared field is nullable.** `in_progress` is a real draft state — it
is what makes a multi-step wizard possible, where the applicant saves a step
and closes the tab. Completeness is therefore a property of the
`in_progress -> submitted` transition, not of the table; the submit ticket
enforces it. A `NOT NULL` here would mean the wizard could not save until it
was finished, which is the same as not having a wizard.

**Nothing here may be returned by a route.** Serialize through
models/schemas/kyc.py, whose default masks; the unmasked schema is gated on
`kyc:application:read_pii`.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base
from remitx_api.models.orm.kyc_lifecycle import (
    MAX_RISK_SCORE,
    MIN_RISK_SCORE,
    OPEN_STATUSES,
    KycIdType,
    KycSourceOfFunds,
    KycStatus,
    sql_value_list,
)

# The override columns travel together: a rating with no reason, or a reason
# with nobody answerable for it, is not an override the log can defend.
_OVERRIDE_COLUMNS = (
    "risk_rating_override",
    "risk_rating_override_reason",
    "risk_rating_overridden_by_user_id",
    "risk_rating_overridden_at",
)


class KycApplication(Base):
    __tablename__ = "kyc_applications"
    __table_args__ = (
        CheckConstraint(
            f"id_type IS NULL OR id_type IN ({sql_value_list(KycIdType)})",
            name="kyc_applications_id_type_valid",
        ),
        CheckConstraint(
            "source_of_funds IS NULL OR source_of_funds IN "
            f"({sql_value_list(KycSourceOfFunds)})",
            name="kyc_applications_source_of_funds_valid",
        ),
        CheckConstraint(
            "tier_granted IS NULL OR tier_granted >= 0",
            name="kyc_applications_tier_granted_non_negative",
        ),
        CheckConstraint("version >= 1", name="kyc_applications_version_positive"),
        CheckConstraint(
            "expected_monthly_volume_zar IS NULL OR expected_monthly_volume_zar >= 0",
            name="kyc_applications_expected_monthly_volume_non_negative",
        ),
        CheckConstraint(
            "risk_score IS NULL OR "
            f"(risk_score >= {MIN_RISK_SCORE} AND risk_score <= {MAX_RISK_SCORE})",
            name="kyc_applications_risk_score_in_range",
        ),
        CheckConstraint(
            "("
            + " AND ".join(f"{column} IS NULL" for column in _OVERRIDE_COLUMNS)
            + ") OR ("
            + " AND ".join(f"{column} IS NOT NULL" for column in _OVERRIDE_COLUMNS)
            + ")",
            name="kyc_applications_risk_override_complete",
        ),
        # One application in flight per user, enforced by the database rather
        # than a read-then-write check in Python, which two concurrent
        # submissions would both pass. Partial, so the rejected and approved
        # history a user accumulates does not block their next attempt.
        #
        # `sqlite_where` as well as `postgresql_where` on purpose: with only
        # the Postgres form the index degrades to a plain unique index in the
        # SQLite test database, where it would fire on a user's *second*
        # application of any status and make the constraint untestable.
        Index(
            "uq_kyc_applications_one_open_per_user",
            "user_id",
            unique=True,
            postgresql_where=text(f"status IN ({sql_value_list(OPEN_STATUSES)})"),
            sqlite_where=text(f"status IN ({sql_value_list(OPEN_STATUSES)})"),
        ),
        # The reviewer queue is "everything waiting on me, oldest first".
        Index("idx_kyc_applications_status_submitted_at", "status", "submitted_at"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        Text,
        ForeignKey("kyc_application_statuses.status", ondelete="RESTRICT"),
        nullable=False,
        default=KycStatus.IN_PROGRESS.value,
        server_default=KycStatus.IN_PROGRESS.value,
    )

    # --- Declared identity (brief §4, "Mock KYC") -------------------------
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Every country column is a `countries.code`. The Postgres constraints are
    # NOT VALID: they bind every write from the migration on, but rows declared
    # before it are history and are not rewritten to satisfy them.
    nationality: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=True,
    )
    # With `issuing_country`, names a `kyc_identity_schemes` row: `US` +
    # `national_id` is a Social Security Number.
    id_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    issuing_country: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=True,
    )
    # Stored as the scheme's validator normalised it — an SSN without hyphens.
    id_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Required when the scheme `requires_expiry` (passports), and in the future
    # on the day it is saved and the day it is submitted.
    id_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    mobile_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Declared on the application, not read off `users.email`: the applicant
    # may bank under a different address than they signed up with, and the
    # reviewer needs to see what was claimed here.
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_of_funds: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured rather than one free-text blob so the masked view can show
    # city and country — enough for a reviewer to sanity-check jurisdiction —
    # while the street address stays behind `kyc:application:read_pii`.
    residential_line1: Mapped[str | None] = mapped_column(Text, nullable=True)
    residential_line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    residential_city: Mapped[str | None] = mapped_column(Text, nullable=True)
    residential_postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Must be a country RemitX `operates_in` — checked on save and on submit.
    residential_country: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=True,
    )

    # Free text, required when `source_of_funds` is `other` — "other" alone
    # tells a reviewer nothing.
    source_of_funds_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # What the applicant expects to send per month. Compared against the tier 1
    # monthly limit in `kyc_tiers` by the risk rules, never enforced as a limit.
    expected_monthly_volume_zar: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    # --- PEP self-declaration (FICA §21F-§21H) ----------------------------
    # Self-declared and reviewed by a human. Nothing here has been checked
    # against a sanctions list, PEP database or adverse-media source, and no
    # screen may say otherwise.
    #
    # Three questions rather than one "are you a PEP?", in FICA's own terms, so
    # the answer says which kind — a foreign official is not a domestic one.
    is_domestic_prominent_influential_person: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    is_foreign_prominent_public_official: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    is_pep_family_or_close_associate: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    # Required on submission when any of the three is true.
    pep_relationship: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("kyc_pep_relationships.relationship", ondelete="RESTRICT"),
        nullable=True,
    )
    pep_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    pep_country: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=True,
    )
    pep_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Where the applicant's wealth came from, as opposed to where this money
    # came from. Enhanced due diligence: required on submission for a PEP, and
    # for any approval to a tier whose `kyc_tiers.requires_source_of_wealth`.
    source_of_wealth: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Review outcome ---------------------------------------------------
    # Set by the in_progress -> submitted transition and never cleared, so a
    # more_info_required round trip keeps the original submission time.
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # When the applicant last consented, on the review step, to RemitX
    # processing this application for FICA due diligence. Re-stamped on every
    # applicant submit — including after more_info_required — because the
    # draft they are consenting to may have changed. Distinct from
    # `submitted_at`, which is the first time this application entered review
    # and is never moved. Null if the application reached `submitted` through
    # a lifecycle transition that was not the applicant's submit endpoint.
    processing_consented_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # The *computed* assessment, written at every submission by the rules in
    # services/kyc_risk_rules.py. Never written by a reviewer — an override
    # goes in the columns below, so both values survive.
    risk_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    risk_rating: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("kyc_risk_ratings.rating", ondelete="RESTRICT"),
        nullable=True,
    )
    # A reviewer's override of `risk_rating`, with the mandatory reason. Kept
    # across a more_info_required round trip: resubmitting rescores the
    # application but does not quietly undo a reviewer's judgement.
    risk_rating_override: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("kyc_risk_ratings.rating", ondelete="RESTRICT"),
        nullable=True,
    )
    risk_rating_override_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    risk_rating_overridden_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    risk_rating_overridden_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    tier_granted: Mapped[int | None] = mapped_column(
        SmallInteger,
        ForeignKey("kyc_tiers.tier", ondelete="RESTRICT"),
        nullable=True,
    )
    # Ongoing due diligence (FICA §21C). Written on approval; nothing reads it
    # yet — see models/orm/kyc_lifecycle.py for why it exists anyway.
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Optimistic concurrency. Two reviewers with the detail page open each hold
    # the version they were shown; `KycController.transition` updates only the
    # row still at that version, so the second decision fails with 409 instead
    # of overwriting the first. Not SQLAlchemy's `version_id_col`, which
    # compares against whatever the *server* last loaded — and each request
    # loads the row fresh, so it would never see the conflict.
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    @property
    def declares_pep(self) -> bool:
        """Yes to any of the three PEP questions."""
        return any(
            (
                self.is_domestic_prominent_influential_person,
                self.is_foreign_prominent_public_official,
                self.is_pep_family_or_close_associate,
            )
        )

    @property
    def effective_risk_rating(self) -> str | None:
        """The rating decisions are made against: the override if a reviewer
        set one, the computed rating otherwise."""
        return self.risk_rating_override or self.risk_rating
