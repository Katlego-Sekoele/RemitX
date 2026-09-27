"""Append-only record of privileged actions and of looks at customer data.

Two kinds of entry share one table. A *mutation* — a KYC decision, a cash-in
confirmation, a role grant — records what changed. A *sensitive read* — opening
an application's full PII, viewing an identity document — records only that it
happened, to whom and by whom. Logging reads is the half that is easy to skip
and the half POPIA cares about most: "who looked at whose ID document" should
be an answerable question.

One table written through one helper rather than four near-identical shapes:
`services/audit_service.record_audit` is the only writer, and it stages into
the caller's transaction so an action and its audit entry land together or not
at all.

Nothing here updates or deletes. There is no repository method for either, no
ORM relationship that could cascade into the table, and the actions enum is the
only source of action strings — a typo fails at import rather than writing a
row nobody will ever match on. Issue #54 owns the rest of this feature: the
database-level `UPDATE`/`DELETE` denial, `GET /admin/audit`, and the actions
beyond the one this module's first caller writes.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class AuditAction(StrEnum):
    """Dotted, past tense, and closed.

    Grows as the privileged paths that write it are built (#54); an action
    string that is not a member here cannot be recorded.
    """

    AUDIT_LOG_VIEWED = "audit.log.viewed"
    KYC_DOCUMENT_VIEWED = "kyc.document.viewed"
    KYC_DOCUMENT_REMOVED = "kyc.document.removed"
    KYC_PII_VIEWED = "kyc.pii.viewed"
    KYC_APPLICATION_DECIDED = "kyc.application.decided"
    CASHIN_CONFIRMED = "cashin.confirmed"
    CASHOUT_BANK_ACCOUNT_VERIFIED = "cashout.bank_account.verified"
    CASHOUT_BANK_ACCOUNT_REJECTED = "cashout.bank_account.rejected"
    ROLE_GRANTED = "role.granted"
    ROLE_REVOKED = "role.revoked"
    SETTLEMENT_RETRY_ENQUEUED = "settlement.retry_enqueued"
    SETTLEMENT_RECLAIM_RAN = "settlement.reclaim.ran"


# Stable id for entries that describe a look at the audit log itself (not a row).
AUDIT_LOG_INDEX_SUBJECT_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


class AuditSubject(StrEnum):
    """What an entry is *about*, so a compliance officer can ask "everything
    that happened to this thing" without knowing which actions exist."""

    KYC_DOCUMENT = "kyc_document"
    KYC_APPLICATION = "kyc_application"
    DEPOSIT = "deposit"
    BANK_ACCOUNT = "bank_account"
    USER_ROLE = "user_role"
    AUDIT_LOG = "audit_log"
    SETTLEMENT_QUOTE = "settlement_quote"


# JSONB on Postgres for indexable containment queries; plain JSON on the
# SQLite the test suite builds, which has no JSONB.
_JSON = JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        # The two questions this table is asked: "what did this person do" and
        # "what happened to this record".
        Index("idx_audit_log_actor_created_at", "actor_user_id", "created_at"),
        Index("idx_audit_log_subject", "subject_type", "subject_id"),
        Index("idx_audit_log_created_at", "created_at"),
    )

    audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    # Never null — every entry is a real staff member (including whoever ran
    # statement reconciliation on the admin portal).
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Scrubbed of PII by construction: ids, enum values and counts only. For a
    # read, `before` stays null and `after` carries where the subject sits —
    # which application a document belongs to, say — because a document id
    # alone does not answer "whose".
    before: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Correlates every entry written while serving one request.
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set in Python, like users.created_at: SQLite's second precision cannot
    # order two entries written in the same request.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
