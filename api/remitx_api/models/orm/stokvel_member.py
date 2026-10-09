"""
A user's membership of a stokvel, current (`left_at` null) or former.

`id`, packed into `bytes32`, is the member's on-chain `memberId`. Someone who
leaves and rejoins gets a new row, so a member id is never reused.
`account_id` is the member's fiat account in the Stokvel currency that pays
their contributions.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


class StokvelMember(Base):
    __tablename__ = "stokvel_members"
    __table_args__ = (
        # One active membership per user per stokvel; former rows stay as history
        Index(
            "uq_stokvel_members_active",
            "stokvel_id",
            "user_id",
            unique=True,
            postgresql_where=text("left_at IS NULL"),
            sqlite_where=text("left_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    stokvel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("stokvels.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.account_id"), nullable=False
    )
    # The accepted invitation; null for the Organiser
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("stokvel_invitations.id"), nullable=True, unique=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
