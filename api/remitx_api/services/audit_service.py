"""The one way an audit entry gets written.

`record_audit` stages the row and flushes it; it deliberately does not commit.
An audit entry that commits independently of the action it describes can
outlive a rolled-back action or, worse, be lost while the action stands — and
the second failure is the one that leaves the record wrong in the direction
that matters. The caller owns the transaction (`db_transaction`, per
CLAUDE.md), so the action and its entry land together.

`before` and `after` carry ids, enum values and counts. Never PII: an audit log
that has to be protected as carefully as the thing it audits has defeated
itself.
"""

from __future__ import annotations

import uuid

from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditLog, AuditSubject
from remitx_api.request_context import current_request_id


def record_audit(
    *,
    actor_user_id: uuid.UUID,
    action: AuditAction,
    subject_type: AuditSubject,
    subject_id: uuid.UUID,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Stage one entry into the caller's transaction.

    Typed parameters rather than strings: an action or subject that is not in
    the enums fails at import, not in a row nobody will ever match on.

    `request_id` defaults to the one `RequestIdMiddleware` assigned this
    request, so entries written while serving it correlate without every
    controller having to carry the value down.
    """
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action.value,
        subject_type=subject_type.value,
        subject_id=subject_id,
        before=before,
        after=after,
        reason=reason,
        request_id=request_id or current_request_id(),
    )
    db.session.add(entry)
    db.session.flush()
    return entry
