"""Read-only access to the append-only audit log."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from remitx_api.models.orm.audit_log import AuditLog
from remitx_api.models.orm.user import User


class AuditLogRepository:
    def list_entries(
        self,
        session: Session,
        *,
        actor_user_id: uuid.UUID | None = None,
        action: str | None = None,
        subject_type: str | None = None,
        subject_id: uuid.UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[tuple[AuditLog, str]]:
        stmt: Select = (
            select(AuditLog, User.email)
            .join(User, User.id == AuditLog.actor_user_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.audit_id.desc())
            .limit(limit)
        )
        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        if subject_type is not None:
            stmt = stmt.where(AuditLog.subject_type == subject_type)
        if subject_id is not None:
            stmt = stmt.where(AuditLog.subject_id == subject_id)
        if created_after is not None:
            stmt = stmt.where(AuditLog.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(AuditLog.created_at < created_before)
        if before is not None:
            stmt = stmt.where(AuditLog.created_at < before)
        return list(session.execute(stmt).all())
