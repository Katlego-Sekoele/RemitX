"""Privileged-action audit log — listing, meta-audit, and append-only storage."""

import uuid
from unittest.mock import patch

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditLog, AuditSubject
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user_role import UserRole
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services.audit_service import record_audit
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
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


def test_list_audit_paginates_with_before_cursor():
    auditor = make_user("pager")

    with rbac_client(auditor, permissions=(PermissionCode.AUDIT_READ,)) as client:
        for _ in range(5):
            record_audit(
                actor_user_id=auditor.id,
                action=AuditAction.KYC_PII_VIEWED,
                subject_type=AuditSubject.KYC_APPLICATION,
                subject_id=uuid.uuid4(),
            )
            db.session.commit()

        first = client.get(
            "/admin/audit",
            params={"limit": 2, "action": AuditAction.KYC_PII_VIEWED.value},
        )
        assert first.status_code == 200
        assert len(first.json()) == 2

        before = first.json()[-1]["created_at"]
        second = client.get(
            "/admin/audit",
            params={
                "limit": 2,
                "before": before,
                "action": AuditAction.KYC_PII_VIEWED.value,
            },
        )
        assert second.status_code == 200
        first_ids = {row["audit_id"] for row in first.json()}
        second_ids = {row["audit_id"] for row in second.json()}
        assert first_ids.isdisjoint(second_ids)
        assert len(second.json()) >= 1


def test_failed_audit_write_rolls_back_role_grant():
    admin = make_user("grant-admin")
    target = make_user("grant-target")

    def _boom(**_kwargs):
        raise SQLAlchemyError("audit insert failed")

    with rbac_client(admin, roles=("iam_admin",)) as client:
        UserRepository().save(target)
        with patch(
            "remitx_api.controllers.user_role_controller.record_audit",
            side_effect=_boom,
        ):
            with pytest.raises(SQLAlchemyError):
                client.post(
                    f"/admin/users/{target.id}/roles",
                    json={
                        "role": "support_agent",
                        "reason": "Joining the compliance rota this quarter.",
                    },
                )
        active = list(
            db.session.scalars(
                select(UserRole).where(
                    UserRole.user_id == target.id,
                    UserRole.revoked_at.is_(None),
                )
            )
        )

    assert active == []


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
