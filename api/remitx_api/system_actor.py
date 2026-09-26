"""The dedicated user row privileged automation acts as in the audit log.

``audit_log.actor_user_id`` is never null; statement auto-matching and similar
jobs attribute their entries here rather than inventing a null actor.
"""

from __future__ import annotations

import uuid

from remitx_api.extensions import db
from remitx_api.models.orm.user import User
# Fixed id so migrations, tests, and runtime agree without a lookup table.
SYSTEM_ACTOR_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
SYSTEM_ACTOR_CLERK_ID = "user_remitx_system"
SYSTEM_ACTOR_EMAIL = "system@internal.remitx"
SYSTEM_ACTOR_BASE_REFERENCE = "system1"


def ensure_system_actor() -> uuid.UUID:
    """Return the system actor's user id, creating the row on first use."""
    if db.session.get(User, SYSTEM_ACTOR_USER_ID) is not None:
        return SYSTEM_ACTOR_USER_ID
    db.session.add(
        User(
            id=SYSTEM_ACTOR_USER_ID,
            clerk_user_id=SYSTEM_ACTOR_CLERK_ID,
            email=SYSTEM_ACTOR_EMAIL,
            first_name="System",
            base_reference=SYSTEM_ACTOR_BASE_REFERENCE,
        )
    )
    db.session.flush()
    return SYSTEM_ACTOR_USER_ID
