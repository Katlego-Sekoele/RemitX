"""Listing the privileged-action audit log (and recording that it was read)."""

from __future__ import annotations

import uuid
from datetime import datetime

from remitx_api.db.transaction import db_transaction
from remitx_api.models.orm.audit_log import (
    AUDIT_LOG_INDEX_SUBJECT_ID,
    AuditAction,
    AuditLog,
    AuditSubject,
)
from remitx_api.models.schemas.audit import AuditLogListFilters, AuditLogRead
from remitx_api.repositories.audit_log_repository import AuditLogRepository
from remitx_api.services.audit_service import record_audit

DEFAULT_AUDIT_PAGE_SIZE = 50
MAX_AUDIT_PAGE_SIZE = 200


class AuditController:
    def __init__(self) -> None:
        self._entries = AuditLogRepository()

    @db_transaction
    def list_audit(
        self,
        *,
        actor_user_id: uuid.UUID,
        actor_user_id_filter: uuid.UUID | None = None,
        action: str | None = None,
        subject_type: str | None = None,
        subject_id: uuid.UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = DEFAULT_AUDIT_PAGE_SIZE,
        before: datetime | None = None,
    ) -> list[AuditLogRead]:
        """Return one page of entries and record that this page was viewed."""
        from remitx_api.extensions import db

        page_size = min(max(limit, 1), MAX_AUDIT_PAGE_SIZE)
        rows = self._entries.list_entries(
            db.session,
            actor_user_id=actor_user_id_filter,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            created_after=created_after,
            created_before=created_before,
            limit=page_size,
            before=before,
        )
        filters = AuditLogListFilters(
            actor_user_id=actor_user_id_filter,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            created_after=created_after,
            created_before=created_before,
        )
        record_audit(
            actor_user_id=actor_user_id,
            action=AuditAction.AUDIT_LOG_VIEWED,
            subject_type=AuditSubject.AUDIT_LOG,
            subject_id=AUDIT_LOG_INDEX_SUBJECT_ID,
            after={
                "limit": page_size,
                "before": before.isoformat() if before else None,
                "filters": filters.model_dump(mode="json", exclude_none=True),
            },
        )
        return [_to_read(entry, email) for entry, email in rows]


def _to_read(entry: AuditLog, actor_email: str) -> AuditLogRead:
    return AuditLogRead(
        audit_id=entry.audit_id,
        actor_user_id=entry.actor_user_id,
        actor_email=actor_email,
        action=entry.action,
        subject_type=entry.subject_type,
        subject_id=entry.subject_id,
        before=entry.before,
        after=entry.after,
        reason=entry.reason,
        request_id=entry.request_id,
        created_at=entry.created_at,
    )
