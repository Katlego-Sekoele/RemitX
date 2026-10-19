"""Privileged-action audit log — admin read models."""

import uuid
from datetime import datetime

from remitx_api.models.schemas.base import Schema, UtcDateTime


class AuditLogRead(Schema):
    audit_id: uuid.UUID
    actor_user_id: uuid.UUID
    actor_email: str
    action: str
    subject_type: str
    subject_id: uuid.UUID
    before: dict | None
    after: dict | None
    reason: str | None
    request_id: str | None
    created_at: UtcDateTime


class AuditLogListFilters(Schema):
    """Echo of the filters used for a list request (for tests and meta-audit)."""

    actor_user_id: uuid.UUID | None = None
    action: str | None = None
    subject_type: str | None = None
    subject_id: uuid.UUID | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
