"""Permission pairs that should not end up on one person.

Rows, not constants: separation-of-duties rules change as a team grows or
shrinks, and changing one should be an ``UPDATE``, not a build and a deploy.
The access page reads them from ``GET /admin/roles/toxic-combinations``, so
the warning a granter sees is the same row the grant is checked against.

These warn, they do not block. In a four-person team the person who confirms
cash-in is sometimes the only one around to complete a payout, and a hard
refusal would only push the grant into a psql session where nothing records
it. The grant goes through, the granter is told, and
``user_roles.toxic_combination_acknowledged`` records that they were told.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class ToxicCombination(Base):
    __tablename__ = "toxic_combinations"
    __table_args__ = (
        CheckConstraint(
            "permission_a_id <> permission_b_id",
            name="toxic_combinations_distinct_permissions",
        ),
        UniqueConstraint(
            "permission_a_id",
            "permission_b_id",
            name="uq_toxic_combinations_pair",
        ),
    )

    toxic_combination_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    permission_a_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("permissions.permission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_b_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("permissions.permission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
