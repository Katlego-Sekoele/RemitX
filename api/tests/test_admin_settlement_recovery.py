"""Staff settlement recovery endpoints."""

from decimal import Decimal

from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditLog
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.transaction import (
    STATUS_PROCESSING,
    Transaction,
)
from remitx_api.services import queue_service, remittance_service
from sqlalchemy import select, update
from tests.platform_account_helpers import seed_platform_accounts
from tests.rbac_helpers import make_user, rbac_client
from tests.test_remittance_service import (
    _fund_and_quote,
    _make_sender_and_beneficiary,
    _store_rate,
)

STUCK = "/admin/operations/settlements/stuck"
RECLAIM = "/admin/operations/settlements/reclaim-pending"


def _confirm_pending_remittance(enqueued):
    _store_rate("18.50")
    _store_rate("16.22", base_currency="ZAR", quote_currency="ZWL")
    seed_platform_accounts()
    sender, _recipient, beneficiary = _make_sender_and_beneficiary()
    quote = _fund_and_quote(sender, beneficiary, Decimal("1000"))
    remittance_service.confirm_remittance(sender.id, quote.quote_id)
    enqueued.clear()
    return quote.quote_id


def test_list_stuck_requires_transaction_read():
    with rbac_client(make_user("stuck-denied")) as client:
        assert client.get(STUCK).status_code == 403


def test_retry_requires_settlement_retry_permission(monkeypatch):
    calls = []
    monkeypatch.setattr(
        queue_service, "enqueue_settle_remittance", calls.append
    )

    with rbac_client(
        make_user("stuck-reader"),
        permissions=(PermissionCode.TRANSACTION_READ_ANY,),
    ) as client:
        quote_id = _confirm_pending_remittance(calls)
        retry = client.post(f"/admin/operations/settlements/{quote_id}/retry-enqueue")
        assert retry.status_code == 403


def test_retry_enqueue_for_fully_pending_group(monkeypatch):
    calls = []
    monkeypatch.setattr(
        queue_service, "enqueue_settle_remittance", calls.append
    )

    with rbac_client(
        make_user("treasury"),
        permissions=(
            PermissionCode.TRANSACTION_READ_ANY,
            PermissionCode.SETTLEMENT_RETRY,
        ),
    ) as client:
        quote_id = _confirm_pending_remittance(calls)
        calls.clear()

        stuck = client.get(STUCK)
        assert stuck.status_code == 200
        row = next(r for r in stuck.json() if r["quote_id"] == str(quote_id))
        assert row["recovery_kind"] == "retry_enqueue"
        assert row["pending_leg_count"] == 7

        retry = client.post(f"/admin/operations/settlements/{quote_id}/retry-enqueue")
        assert retry.status_code == 200
        assert retry.json() == {"quote_id": str(quote_id), "enqueued": True}
        assert calls == [str(quote_id)]

        audit = db.session.scalars(
            select(AuditLog).where(
                AuditLog.action == AuditAction.SETTLEMENT_RETRY_ENQUEUED.value
            )
        ).all()
        assert any(entry.subject_id == quote_id for entry in audit)


def test_retry_refuses_processing_group(monkeypatch):
    calls = []
    monkeypatch.setattr(
        queue_service, "enqueue_settle_remittance", calls.append
    )

    with rbac_client(
        make_user("treasury-2"),
        permissions=(
            PermissionCode.TRANSACTION_READ_ANY,
            PermissionCode.SETTLEMENT_RETRY,
        ),
    ) as client:
        quote_id = _confirm_pending_remittance(calls)
        db.session.execute(
            update(Transaction)
            .where(Transaction.quote_id == quote_id)
            .values(status=STATUS_PROCESSING)
        )
        db.session.commit()

        retry = client.post(f"/admin/operations/settlements/{quote_id}/retry-enqueue")
        assert retry.status_code == 409
        assert "settlement_not_retryable" in retry.json()["detail"]
        assert calls == []


def test_reclaim_pending_enqueues_all_safe_groups(monkeypatch):
    calls = []
    monkeypatch.setattr(
        queue_service, "enqueue_settle_remittance", calls.append
    )

    with rbac_client(
        make_user("treasury-3"),
        permissions=(
            PermissionCode.TRANSACTION_READ_ANY,
            PermissionCode.SETTLEMENT_RETRY,
        ),
    ) as client:
        quote_id = _confirm_pending_remittance(calls)
        calls.clear()

        response = client.post(RECLAIM, json={"min_age_seconds": 0})
        assert response.status_code == 200
        body = response.json()
        assert str(quote_id) in body["requeued_quote_ids"]
        assert str(quote_id) in calls
