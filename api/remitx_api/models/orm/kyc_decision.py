"""Append-only record of every reviewer action on a KYC application.

Append-only is the whole point: `kyc_applications.status` tells you where an
application is now, and this tells you how it got there and who is answerable
for each step. Nothing updates or deletes a row here — a reversal is a new
decision, not an edit.

`from_status` is not in the ticket's column list and is kept anyway: with it,
the log alone reconstructs the path an application took, so an auditor never
has to trust that the code's transition table was the same when the row was
written as it is today.

The general audit log (issue #54) is a separate, wider thing. This table
carries what the KYC domain needs to answer a compliance question about one
application without joining to it.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base
from remitx_api.models.orm.kyc_lifecycle import (
    APPLICATION_STATUSES,
    DECISION_STATUSES,
    KycReasonCode,
    sql_value_list,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class KycDecision(Base):
    __tablename__ = "kyc_decisions"
    __table_args__ = (
        CheckConstraint(
            f"decision IN ({sql_value_list(DECISION_STATUSES)})",
            name="kyc_decisions_decision_valid",
        ),
        CheckConstraint(
            f"from_status IN ({sql_value_list(APPLICATION_STATUSES)})",
            name="kyc_decisions_from_status_valid",
        ),
        CheckConstraint(
            f"reason_code IS NULL OR reason_code IN ({sql_value_list(KycReasonCode)})",
            name="kyc_decisions_reason_code_valid",
        ),
        # "Show me this application's history, oldest first."
        Index(
            "idx_kyc_decisions_application_decided_at", "application_id", "decided_at"
        ),
    )

    decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("kyc_applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The status the application moved *to*, drawn from DECISION_STATUSES.
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free text for the applicant — "the address on your utility bill does not
    # match the one you declared". Named fields go here, which is what makes
    # more_info_required more useful than a bare rejection.
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable for a future automated decision (a sanctions screen declining an
    # application with no human involved). `KycController.transition` requires
    # an actor for every decision a human can make, so in practice a NULL here
    # means "the system did this", never "we lost track of who did".
    #
    # RESTRICT, not SET NULL: a compliance log that forgets who decided when
    # the reviewer's account is deleted is not a compliance log.
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
