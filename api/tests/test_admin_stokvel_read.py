"""Admin stokvel contract read and rounds list."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from remitx_api.models.orm.permission import PermissionCode
from remitx_api.services.stokvel_admin_read import AdminStokvelRoundView
from tests.rbac_helpers import make_user, rbac_client

CONTRACT = "/admin/stokvel-contract"
ROUNDS = "/admin/stokvels/rounds"


def test_contract_read_requires_permission(monkeypatch):
    monkeypatch.setattr(
        "remitx_api.services.stokvel_admin_read.read_contract_status",
        lambda: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    with rbac_client(make_user("contract-denied")) as client:
        assert client.get(CONTRACT).status_code == 403


def test_contract_read_returns_pause_context(monkeypatch):
    when = datetime(2026, 10, 19, 10, 0, tzinfo=UTC)

    class View:
        address = "0x2f240705314BB79780522635eA47d20072CB8Fe1"
        network = "XRPL EVM Testnet"
        paused = True
        paused_at = when
        paused_reason = "Investigating a failed payout"
        treasury_token_balance = Decimal("110000.00000000")

    monkeypatch.setattr(
        "remitx_api.controllers.stokvel_admin_controller.read_contract_status",
        lambda: View(),
    )

    with rbac_client(
        make_user("contract-read"),
        permissions=(PermissionCode.STOKVEL_CONTRACT_PAUSE,),
    ) as client:
        response = client.get(CONTRACT)
    assert response.status_code == 200
    assert response.json() == {
        "address": View.address,
        "network": View.network,
        "paused": True,
        "paused_at": when.isoformat(),
        "paused_reason": View.paused_reason,
        "treasury_token_balance": "110000.00000000",
    }


def test_rounds_list_requires_permission():
    with rbac_client(make_user("rounds-denied")) as client:
        assert client.get(ROUNDS).status_code == 403


def test_rounds_list_returns_admin_rows(monkeypatch):
    stokvel_id = uuid.uuid4()
    when = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    row = AdminStokvelRoundView(
        stokvel_id=stokvel_id,
        stokvel_name="December groceries",
        round=1,
        total_rounds=3,
        recipient_name="Sipho Khumalo",
        paid_count=3,
        member_count=3,
        payout_time=when,
        release_status="pending",
        release_tx_hash=None,
        manual_release_allowed=True,
    )
    monkeypatch.setattr(
        "remitx_api.controllers.stokvel_admin_controller.list_admin_rounds",
        lambda: [row],
    )

    with rbac_client(
        make_user("rounds-list"),
        permissions=(PermissionCode.STOKVEL_ROUND_FINALISE,),
    ) as client:
        response = client.get(ROUNDS)
    assert response.status_code == 200
    assert response.json() == [
        {
            "stokvel_id": str(stokvel_id),
            "stokvel_name": "December groceries",
            "round": 1,
            "total_rounds": 3,
            "recipient_name": "Sipho Khumalo",
            "paid_count": 3,
            "member_count": 3,
            "payout_time": when.isoformat(),
            "release_status": "pending",
            "release_tx_hash": None,
            "manual_release_allowed": True,
        }
    ]
