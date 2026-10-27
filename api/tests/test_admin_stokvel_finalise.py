"""Admin manual finalise (R3-10, #247)."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.audit_log import AuditAction, AuditLog, AuditSubject
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_payout import StokvelPayoutReleaseStatus
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.services import queue_service
from remitx_api.services.stokvel_contract_read import (
    FinaliseReadiness,
    classify_finalise,
)
from sqlalchemy import select
from tests.rbac_helpers import make_user, rbac_client

PERMISSION = PermissionCode.STOKVEL_ROUND_FINALISE


def _url(stokvel_id, round_=0) -> str:
    return f"/admin/stokvels/{stokvel_id}/rounds/{round_}/finalise"


def _seed(organiser_id, *, status="active", registered=True, rounds=2):
    now = datetime.now(UTC)
    stokvel = Stokvel(
        organiser_user_id=organiser_id,
        name="Savings club",
        currency="ZAR",
        contribution_amount=Decimal("10"),
    )
    db.session.add(stokvel)
    db.session.flush()
    forming = status == StokvelCycleStatus.FORMING.value
    closed = status == StokvelCycleStatus.CLOSED.value
    cycle = StokvelCycle(
        stokvel_id=stokvel.id,
        cycle_number=1,
        status=status,
        total_rounds=None if forming else rounds,
        current_round=None if forming else 0,
        started_at=None if forming else now,
        registered_at=None if forming or not registered else now,
        closed_at=now if closed else None,
    )
    db.session.add(cycle)
    db.session.flush()
    stokvel.current_cycle_id = cycle.id
    if not forming and rounds:
        due = now - timedelta(hours=1)
        start = due - timedelta(days=1)
        deadline = due - timedelta(minutes=1)
        for round_ in range(rounds):
            db.session.add(
                StokvelRound(
                    cycle_id=cycle.id,
                    round=round_,
                    start_time=start,
                    deadline=deadline,
                    payout_time=due,
                )
            )
    db.session.commit()
    return stokvel, cycle


def _hold_payout(monkeypatch, status, tx_hash=None):
    found = SimpleNamespace(release_status=status, release_tx_hash=tx_hash)
    monkeypatch.setattr(
        "remitx_api.controllers.stokvel_admin_controller"
        ".StokvelPayoutRepository.get_round_payout",
        lambda self, cycle_id, round_: found,
    )


def _patch(monkeypatch, readiness, paused=False, *, db_ready=True):
    queued = []
    monkeypatch.setattr(
        "remitx_api.controllers.stokvel_admin_controller.is_paused",
        lambda: paused,
    )
    if db_ready:
        monkeypatch.setattr(
            "remitx_api.controllers.stokvel_admin_controller"
            ".round_manual_release_allowed",
            lambda **kwargs: True,
        )
    monkeypatch.setattr(
        "remitx_api.controllers.stokvel_admin_controller.finalise_readiness",
        lambda *args: readiness(*args) if callable(readiness) else readiness,
    )
    monkeypatch.setattr(
        queue_service,
        "enqueue_release_pool",
        lambda cycle_id, round_: queued.append((cycle_id, round_)),
    )
    return queued


def test_finalise_requires_the_round_permission(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    user = make_user("finalise-denied")
    with rbac_client(
        user, permissions=(PermissionCode.STOKVEL_CONTRACT_PAUSE,)
    ) as client:
        stokvel, _cycle = _seed(user.id)
        response = client.post(_url(stokvel.id))
    assert response.status_code == 403
    assert queued == []


def test_a_ready_round_is_queued_and_audited(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    user = make_user("finalise-ready")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, cycle = _seed(user.id)
        response = client.post(_url(stokvel.id))
        assert response.status_code == 202
        assert response.json() == {
            "stokvel_id": str(stokvel.id),
            "cycle_id": str(cycle.id),
            "cycle_number": 1,
            "round": 0,
        }
        assert queued == [(str(cycle.id), 0)]
        entry = db.session.scalar(
            select(AuditLog).where(
                AuditLog.action == AuditAction.STOKVEL_ROUND_FINALISED_MANUALLY.value
            )
        )
        assert entry is not None
        assert entry.subject_type == AuditSubject.STOKVEL.value
        assert entry.subject_id == stokvel.id
        assert entry.actor_user_id == user.id
        assert entry.after == {
            "cycle_number": 1,
            "round": 0,
            "release_status": None,
            "tx_hash": None,
            "enqueued": True,
        }


def test_a_round_that_is_not_ready_is_refused(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.NOT_YET)
    user = make_user("finalise-early")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id)
        response = client.post(_url(stokvel.id))
        assert response.status_code == 409
        assert response.json()["code"] == "round_not_finalisable"
        assert response.json()["detail"] == "This round can't be paid out yet."
        assert queued == []
        assert (
            db.session.scalar(
                select(AuditLog).where(
                    AuditLog.action
                    == AuditAction.STOKVEL_ROUND_FINALISED_MANUALLY.value
                )
            )
            is None
        )


def test_a_round_the_chain_has_released_is_not_queued_again(monkeypatch):
    """Automatic release and this route can both see one round. Once the
    chain says it is finalised, the route queues nothing. The single credit
    when both do run is `record_pool_release`
    (`test_recording_it_again_books_nothing`)."""
    seen = {"n": 0}

    def readiness(*_args):
        seen["n"] += 1
        if seen["n"] == 1:
            return FinaliseReadiness.READY
        return FinaliseReadiness.ALREADY

    queued = _patch(monkeypatch, readiness)
    user = make_user("finalise-twice")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, cycle = _seed(user.id)
        cycle_id = str(cycle.id)
        first = client.post(_url(stokvel.id))
        second = client.post(_url(stokvel.id))
        assert first.status_code == 202
        assert second.status_code == 409
        assert second.json()["code"] == "round_already_finalised"
        assert queued == [(cycle_id, 0)]


def test_chain_refusals(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.ALREADY)
    user = make_user("finalise-already")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id)
        response = client.post(_url(stokvel.id))
    assert response.status_code == 409
    assert response.json()["code"] == "round_already_finalised"
    assert queued == []


@pytest.mark.parametrize(
    "readiness",
    [FinaliseReadiness.NO_OPEN_CYCLE, FinaliseReadiness.UNKNOWN_STOKVEL],
)
def test_a_registered_cycle_missing_on_chain_is_not_a_retry(
    monkeypatch, caplog, readiness
):
    queued = _patch(monkeypatch, readiness)
    user = make_user(f"finalise-mismatch-{readiness.value}")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id)
        with caplog.at_level(logging.ERROR):
            response = client.post(_url(stokvel.id))
        assert response.status_code == 503
        assert response.json()["code"] == "stokvel_chain_mismatch"
        assert "try again" not in response.json()["detail"].lower()
        assert queued == []
        assert (
            db.session.scalar(
                select(AuditLog).where(
                    AuditLog.action
                    == AuditAction.STOKVEL_ROUND_FINALISED_MANUALLY.value
                )
            )
            is None
        )
    assert "stokvel.finalise_chain_mismatch" in caplog.text


@pytest.mark.parametrize(
    "status",
    [
        StokvelPayoutReleaseStatus.PROCESSING.value,
        StokvelPayoutReleaseStatus.FAILED.value,
    ],
)
def test_a_payout_that_is_not_pending_is_not_queued(monkeypatch, status):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    _hold_payout(monkeypatch, status)
    user = make_user(f"finalise-payout-{status}")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id)
        response = client.post(_url(stokvel.id))
        assert response.status_code == 409
        assert response.json()["code"] == "round_release_not_pending"
        assert queued == []
        assert (
            db.session.scalar(
                select(AuditLog).where(
                    AuditLog.action
                    == AuditAction.STOKVEL_ROUND_FINALISED_MANUALLY.value
                )
            )
            is None
        )


def test_a_released_payout_row_is_already_finalised(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    _hold_payout(monkeypatch, StokvelPayoutReleaseStatus.RELEASED.value, "0xabc")
    user = make_user("finalise-payout-released")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id)
        response = client.post(_url(stokvel.id))
    assert response.status_code == 409
    assert response.json()["code"] == "round_already_finalised"
    assert queued == []


def test_a_pending_payout_is_still_queued(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    _hold_payout(monkeypatch, StokvelPayoutReleaseStatus.PENDING.value)
    user = make_user("finalise-payout-pending")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, cycle = _seed(user.id)
        response = client.post(_url(stokvel.id))
        assert response.status_code == 202
        assert queued == [(str(cycle.id), 0)]
        entry = db.session.scalar(
            select(AuditLog).where(
                AuditLog.action == AuditAction.STOKVEL_ROUND_FINALISED_MANUALLY.value
            )
        )
        assert entry is not None
        assert entry.after["release_status"] == "pending"
        assert entry.after["enqueued"] is True


def test_a_failed_enqueue_writes_no_audit(monkeypatch):
    _patch(monkeypatch, FinaliseReadiness.READY)

    def boom(cycle_id, round_):
        raise RuntimeError("redis down")

    monkeypatch.setattr(queue_service, "enqueue_release_pool", boom)
    user = make_user("finalise-enqueue-down")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id)
        with pytest.raises(RuntimeError, match="redis down"):
            client.post(_url(stokvel.id))
        assert (
            db.session.scalar(
                select(AuditLog).where(
                    AuditLog.action
                    == AuditAction.STOKVEL_ROUND_FINALISED_MANUALLY.value
                )
            )
            is None
        )


def test_a_closed_cycles_round_is_already_finalised(monkeypatch):
    def readiness(*_args):
        raise AssertionError("a closed cycle is answered from the database")

    queued = _patch(monkeypatch, readiness)
    user = make_user("finalise-closed")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id, status=StokvelCycleStatus.CLOSED.value)
        response = client.post(_url(stokvel.id))
        assert response.status_code == 409
        assert response.json()["code"] == "round_already_finalised"
        assert response.json()["detail"] == "This round has already been paid out."
        past = client.post(_url(stokvel.id, 2))
        assert past.status_code == 409
        assert past.json()["code"] == "round_not_finalisable"
        assert queued == []


def test_a_closed_cycles_round_is_already_finalised_once_the_next_is_forming(
    monkeypatch,
):
    """The worker opens cycle 2 as cycle 1 closes (R2-15, #237)."""

    def readiness(*_args):
        raise AssertionError("a closed cycle is answered from the database")

    queued = _patch(monkeypatch, readiness)
    user = make_user("finalise-closed-next-forming")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id, status=StokvelCycleStatus.CLOSED.value)
        following = StokvelCycle(
            stokvel_id=stokvel.id,
            cycle_number=2,
            status=StokvelCycleStatus.FORMING.value,
        )
        db.session.add(following)
        db.session.flush()
        stokvel.current_cycle_id = following.id
        db.session.commit()
        response = client.post(_url(stokvel.id))
        assert response.status_code == 409
        assert response.json()["code"] == "round_already_finalised"
        past = client.post(_url(stokvel.id, 2))
        assert past.status_code == 409
        assert past.json()["code"] == "round_not_finalisable"
        assert queued == []


def test_a_paused_vault_is_refused_before_the_chain_read(monkeypatch):
    def readiness(*_args):
        raise AssertionError("paused vault must not be read for finalise")

    queued = _patch(monkeypatch, readiness, paused=True)
    user = make_user("finalise-paused")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id)
        response = client.post(_url(stokvel.id))
    assert response.status_code == 503
    assert response.json()["code"] == "stokvel_paused"
    assert queued == []


def test_an_unknown_stokvel_is_not_found(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    user = make_user("finalise-missing")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        response = client.post(_url(uuid.uuid4()))
    assert response.status_code == 404
    assert queued == []


def test_a_cycle_that_has_not_started_is_refused(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    user = make_user("finalise-forming")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id, status=StokvelCycleStatus.FORMING.value)
        response = client.post(_url(stokvel.id))
    assert response.status_code == 409
    assert response.json()["code"] == "cycle_not_open"
    assert queued == []


def test_a_cycle_not_yet_on_chain_is_refused(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    user = make_user("finalise-starting")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id, registered=False)
        response = client.post(_url(stokvel.id))
    assert response.status_code == 409
    assert response.json()["code"] == "cycle_starting"
    assert queued == []


def test_a_round_past_the_cycle_is_not_finalisable(monkeypatch):
    def readiness(*_args):
        raise AssertionError("an out-of-range round is refused before the chain")

    queued = _patch(monkeypatch, readiness)
    user = make_user("finalise-range")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id, rounds=2)
        response = client.post(_url(stokvel.id, 2))
    assert response.status_code == 409
    assert response.json()["code"] == "round_not_finalisable"
    assert queued == []


def test_a_round_outside_uint8_is_rejected(monkeypatch):
    queued = _patch(monkeypatch, FinaliseReadiness.READY)
    user = make_user("finalise-uint")
    with rbac_client(user, permissions=(PERMISSION,)) as client:
        stokvel, _cycle = _seed(user.id)
        response = client.post(_url(stokvel.id, 256))
    assert response.status_code == 422
    assert queued == []


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            dict(
                current_cycle=1,
                cycle_open=True,
                asked_cycle=1,
                is_finalisable=True,
                next_to_finalise=None,
            ),
            FinaliseReadiness.READY,
        ),
        (
            dict(
                current_cycle=1,
                cycle_open=True,
                asked_cycle=1,
                is_finalisable=False,
                next_to_finalise=0,
            ),
            FinaliseReadiness.NOT_YET,
        ),
        (
            dict(
                current_cycle=1,
                cycle_open=False,
                asked_cycle=1,
                is_finalisable=False,
                next_to_finalise=1,
            ),
            FinaliseReadiness.ALREADY,
        ),
        (
            dict(
                current_cycle=1,
                cycle_open=True,
                asked_cycle=1,
                is_finalisable=True,
                next_to_finalise=0,
            ),
            FinaliseReadiness.READY,
        ),
        (
            dict(
                current_cycle=2,
                cycle_open=True,
                asked_cycle=1,
                is_finalisable=True,
                next_to_finalise=1,
            ),
            FinaliseReadiness.ALREADY,
        ),
        (
            dict(
                current_cycle=0,
                cycle_open=False,
                asked_cycle=1,
                is_finalisable=False,
                next_to_finalise=None,
            ),
            FinaliseReadiness.NO_OPEN_CYCLE,
        ),
    ],
)
def test_classify_finalise(kwargs, expected):
    assert classify_finalise(0, **kwargs) is expected


def test_finalise_revert_selectors_match_the_vault_abi():
    from remitx_api.services.stokvel_contract_read import _REVERT_NAMES
    from remitx_worker.stokvel_contract import error_name

    for selector, name in _REVERT_NAMES.items():
        assert error_name(selector) == name
