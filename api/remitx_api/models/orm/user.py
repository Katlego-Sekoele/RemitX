"""Application user, mirrored from Clerk.

Clerk owns credentials and profile data. This table exists so domain records
(beneficiaries, wallets, transfers) have a stable local foreign key, and so
queries can join on identity without calling out to Clerk.

Rows are created just-in-time on the first authenticated request — see
remitx_api/controllers/user_controller.py.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    # Clerk's `sub` claim. Unique so just-in-time provisioning can rely on the
    # database to arbitrate concurrent first requests from the same caller.
    clerk_user_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        index=True,
    )
    # Nullable: not every Clerk sign-in strategy yields an email claim.
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set in Python rather than by the database: SQLite's CURRENT_TIMESTAMP has
    # only second precision, which is too coarse to order rapid inserts.
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
