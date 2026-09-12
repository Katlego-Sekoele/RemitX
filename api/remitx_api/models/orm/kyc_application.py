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
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base
from remitx_api.models.orm.kyc_lifecycle import (
    APPLICATION_STATUSES,
    OPEN_STATUSES,
    KycIdType,
    KycRiskRating,
    KycSourceOfFunds,
    KycStatus,
    sql_value_list,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class KycApplication(Base):
    __tablename__ = "kyc_applications"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({sql_value_list(APPLICATION_STATUSES)})",
            name="kyc_applications_status_valid",
        ),
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
            f"risk_rating IS NULL OR risk_rating IN ({sql_value_list(KycRiskRating)})",
            name="kyc_applications_risk_rating_valid",
        ),
        CheckConstraint(
            "tier_granted IS NULL OR tier_granted >= 0",
            name="kyc_applications_tier_granted_non_negative",
        ),
        CheckConstraint("version >= 1", name="kyc_applications_version_positive"),
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
        nullable=False,
        default=KycStatus.IN_PROGRESS.value,
        server_default=KycStatus.IN_PROGRESS.value,
    )

    # --- Declared identity (brief §4, "Mock KYC") -------------------------
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    # ISO 3166-1 alpha-2, as are `issuing_country` and `residential_country`.
    nationality: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    issuing_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_number: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    residential_country: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Review outcome ---------------------------------------------------
    # Set by the in_progress -> submitted transition and never cleared, so a
    # more_info_required round trip keeps the original submission time.
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    risk_rating: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier_granted: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
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
