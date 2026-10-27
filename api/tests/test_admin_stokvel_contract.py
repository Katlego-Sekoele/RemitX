"""Admin stokvel vault pause and unpause (R3-07, #244)."""

from celery.exceptions import TimeoutError as CeleryTimeoutError
from remitx_api.controllers import stokvel_admin_controller
from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import (
    STOKVEL_CONTRACT_SUBJECT_ID,
    AuditAction,
    AuditLog,
)
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.services import queue_service
from sqlalchemy import select
from tests.rbac_helpers import make_user, rbac_client

PAUSE = "/admin/stokvel-contract/pause"
UNPAUSE = "/admin/stokvel-contract/unpause"
TX = "0x" + "ab" * 32


def test_pause_requires_permission(monkeypatch):
    monkeypatch.setattr(stokvel_admin_controller, "is_paused", lambda: False)
    monkeypatch.setattr(queue_service, "run_pause_contract", lambda: TX)

    with rbac_client(make_user("pause-denied")) as client:
        response = client.post(PAUSE, json={"reason": "rpc outage drill"})
        assert response.status_code == 403


def test_pause_writes_audit_and_returns_hash(monkeypatch):
    monkeypatch.setattr(stokvel_admin_controller, "is_paused", lambda: False)
    monkeypatch.setattr(queue_service, "run_pause_contract", lambda: TX)

    with rbac_client(
        make_user("compliance-pause"),
        permissions=(PermissionCode.STOKVEL_CONTRACT_PAUSE,),
    ) as client:
        response = client.post(PAUSE, json={"reason": "rpc outage drill"})
        assert response.status_code == 200
        assert response.json() == {"tx_hash": TX}

        entry = db.session.scalar(
            select(AuditLog).where(
                AuditLog.action == AuditAction.STOKVEL_CONTRACT_PAUSED.value
            )
        )
        assert entry is not None
        assert entry.subject_id == STOKVEL_CONTRACT_SUBJECT_ID
        assert entry.reason == "rpc outage drill"
        assert entry.after["paused"] is True


def test_pause_refuses_when_already_paused(monkeypatch):
    monkeypatch.setattr(stokvel_admin_controller, "is_paused", lambda: True)

    with rbac_client(
        make_user("compliance-pause-2"),
        permissions=(PermissionCode.STOKVEL_CONTRACT_PAUSE,),
    ) as client:
        response = client.post(PAUSE, json={"reason": "rpc outage drill"})
        assert response.status_code == 409
        assert response.json()["code"] == "stokvel_paused"


def test_pause_reason_length(monkeypatch):
    monkeypatch.setattr(stokvel_admin_controller, "is_paused", lambda: False)

    with rbac_client(
        make_user("compliance-pause-3"),
        permissions=(PermissionCode.STOKVEL_CONTRACT_PAUSE,),
    ) as client:
        short = client.post(PAUSE, json={"reason": "too short"})
        assert short.status_code == 422


def test_pause_timeout_still_writes_audit(monkeypatch):
    monkeypatch.setattr(stokvel_admin_controller, "is_paused", lambda: False)

    def slow_pause():
        raise CeleryTimeoutError()

    monkeypatch.setattr(queue_service, "run_pause_contract", slow_pause)

    with rbac_client(
        make_user("compliance-pause-timeout"),
        permissions=(PermissionCode.STOKVEL_CONTRACT_PAUSE,),
    ) as client:
        response = client.post(PAUSE, json={"reason": "rpc outage drill"})
        assert response.status_code == 504

        entry = db.session.scalar(
            select(AuditLog).where(
                AuditLog.action == AuditAction.STOKVEL_CONTRACT_PAUSED.value
            )
        )
        assert entry is not None
        assert entry.after["tx_hash"] is None


def test_unpause_writes_audit(monkeypatch):
    states = [True, False]

    def is_paused():
        return states[0]

    def run_unpause():
        states[0] = False
        return TX

    monkeypatch.setattr(stokvel_admin_controller, "is_paused", is_paused)
    monkeypatch.setattr(queue_service, "run_unpause_contract", run_unpause)

    with rbac_client(
        make_user("compliance-unpause"),
        permissions=(PermissionCode.STOKVEL_CONTRACT_PAUSE,),
    ) as client:
        response = client.post(UNPAUSE)
        assert response.status_code == 200
        assert response.json() == {"tx_hash": TX}

        entry = db.session.scalar(
            select(AuditLog).where(
                AuditLog.action == AuditAction.STOKVEL_CONTRACT_UNPAUSED.value
            )
        )
        assert entry is not None
        assert entry.after["paused"] is False
