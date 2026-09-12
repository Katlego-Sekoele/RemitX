"""RBAC role catalogue.

``name`` is the stable machine identifier (``compliance_analyst``).
``role_display_name`` is what operators see in admin UI; ``description``
explains what the role is for. ``customer`` exists for reference but is never
assigned through ``user_roles`` — every provisioned user implicitly owns their
own data.
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
