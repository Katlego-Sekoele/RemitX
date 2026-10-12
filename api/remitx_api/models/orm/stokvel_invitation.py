"""
An Organiser's invitation for a user to join a stokvel.

Status moves once, from `pending` to a final value, so the
`status_changed_*` pair is the whole history: inviting again is a new row.
`lapsed` is set when the Organiser starts a cycle (CONTEXT.md), not by time.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


class StokvelInvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REVOKED = "revoked"
    LAPSED = "lapsed"


class StokvelInvitation(Base):
    __tablename__ = "stokvel_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','accepted','declined','revoked','lapsed')",
            name="stokvel_invitations_status_valid",
        ),
        CheckConstraint(
            "invitee_user_id <> invited_by_user_id",
            name="stokvel_invitations_not_self",
        ),
        CheckConstraint(
            "(status = 'pending') = (status_changed_at IS NULL)",
            name="stokvel_invitations_changed_at_matches_status",
        ),
        # Only the invitee answers their own invitation
        CheckConstraint(
            "status NOT IN ('accepted','declined') "
            "OR status_changed_by_user_id = invitee_user_id",
            name="stokvel_invitations_invitee_answers",
        ),
        Index(
            "uq_stokvel_invitations_pending",
            "stokvel_id",
            "invitee_user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    stokvel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("stokvels.id"), nullable=False, index=True
    )
    invitee_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=StokvelInvitationStatus.PENDING.value,
        server_default=StokvelInvitationStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
