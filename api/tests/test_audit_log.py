"""Privileged-action audit log — listing, meta-audit, and append-only storage."""

import uuid

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditLog, AuditSubject
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.services.audit_service import record_audit
from sqlalchemy import select, text
from tests.rbac_helpers import make_user, rbac_client


def _seed_entry(actor_id: uuid.UUID, action: AuditAction = AuditAction.KYC_PII_VIEWED):
    record_audit(
        actor_user_id=actor_id,
        action=action,
        subject_type=AuditSubject.KYC_APPLICATION,
        subject_id=uuid.uuid4(),
    )
    db.session.commit()


def test_list_audit_requires_audit_read():
    officer = make_user("no-audit")

    with rbac_client(
        officer, permissions=(PermissionCode.KYC_APPLICATION_READ,)
    ) as client:
        response = client.get("/admin/audit")

    assert response.status_code == 403


def test_list_audit_records_meta_audit_and_supports_filters():
    auditor = make_user("auditor")

    with rbac_client(auditor, permissions=(PermissionCode.AUDIT_READ,)) as client:
        _seed_entry(auditor.id, AuditAction.KYC_PII_VIEWED)
        _seed_entry(auditor.id, AuditAction.ROLE_GRANTED)

        response = client.get(
            "/admin/audit",
            params={"action": AuditAction.KYC_PII_VIEWED.value, "limit": 10},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["action"] == AuditAction.KYC_PII_VIEWED.value
        assert body[0]["actor_email"] == auditor.email

        entries = list(
            db.session.scalars(
                select(AuditLog).where(
                    AuditLog.action == AuditAction.AUDIT_LOG_VIEWED.value
                )
            )
        )
        assert len(entries) == 1
        meta = entries[0]
        assert meta.actor_user_id == auditor.id
        assert meta.after["filters"]["action"] == AuditAction.KYC_PII_VIEWED.value


@pytest.mark.postgres
def test_audit_log_rejects_update(postgres_app):
    user = make_user("pg-audit")
    token = db.open_session()
    try:
        from remitx_api.repositories.user_repository import UserRepository

        UserRepository().save(user)
        record_audit(
            actor_user_id=user.id,
            action=AuditAction.KYC_DOCUMENT_VIEWED,
            subject_type=AuditSubject.KYC_DOCUMENT,
            subject_id=uuid.uuid4(),
        )
        db.session.commit()
        entry = db.session.scalars(select(AuditLog)).one()
        with pytest.raises(Exception, match="append-only"):
            db.session.execute(
                text("UPDATE audit_log SET action = 'tampered' WHERE audit_id = :id"),
                {"id": entry.audit_id},
            )
            db.session.commit()
        db.session.rollback()
    finally:
        db.close_session(token)
