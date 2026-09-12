"""RBAC role catalogue.

``name`` is the stable machine identifier (``compliance_analyst``).
``role_display_name`` is what operators see in admin UI; ``description``
explains what the role is for.

``is_grantable`` and ``protect_last_holder`` carry the grant rules the API
enforces. They live here, in the row, rather than as role names compared in a
controller: which role is implicit and which must never lose its last holder
are facts about the catalogue, and a name in Python drifts from the catalogue
the moment either changes. ``customer`` is the one non-grantable role — every
provisioned user implicitly owns their own data.
"""

import uuid

from sqlalchemy import Boolean, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    role_display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # False for roles every user holds implicitly, which would mean nothing as
    # a ``user_roles`` row and could not be revoked.
    is_grantable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    # True where an empty role is an outage: revoking the last active grant is
    # refused. ``iam_admin`` is the case it exists for — lose it and nobody can
    # administer access, with no way back short of a psql session.
    protect_last_holder: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
