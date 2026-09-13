"""Assigns operational roles to users.

``customer`` is implicit for every provisioned user and is never stored here.

The table is **append-only**: granting inserts a row, revoking stamps
``revoked_at`` on the one that is live. Nothing is deleted and nothing is
rewritten, so "who could decide KYC applications on 12 September, and who
gave them that?" stays answerable months later — which is the point of
having an access model at all.

Every row carries the *why*, not just the what: ``grant_reason`` and
``revoke_reason`` are required by the API (models/schemas/role.py), so the
history reads as a record a person can review rather than a list of
mutations.

``self_granted`` marks an admin handing themselves a role. That is a
legitimate operation in a small team — blocking it outright only pushes
people to edit the database directly — so it is allowed, flagged, and
surfaced first in the access UI. Visible beats forbidden-then-circumvented.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index(
            "uq_user_roles_active",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    user_role_id: Mapped[uuid.UUID] = mapped_column(
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
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("roles.role_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    # Nullable because rows predating role administration have no reason to
    # record; every grant made through the API has one, enforced there rather
    # than by the column so the message can say what is wrong.
    grant_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True when granter and holder are the same person.
    self_granted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    # The granter was warned that this grant leaves one person holding a
    # toxic combination of permissions (models/orm/toxic_combination.py)
    # and went ahead. False also covers "no warning applied", which is why
    # the detected combinations are returned to the caller on every grant.
    toxic_combination_acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
