"""`GET /stokvels/{id}` (R2-14, #236) on SQLite, which has no row-level security.
The controller scopes by the caller itself."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_payout import (
    StokvelPayout,
    StokvelPayoutReleaseStatus,
)
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.models.orm.transaction import TYPE_FEE, Transaction
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.services.exchange_rate_service import RateUnavailableError
from remitx_api.services.quote_service import TokenRates
from sqlalchemy import select

STOKVELS = "/stokvels"
PAYOUT_TIME = datetime(2026, 11, 3, tzinfo=UTC)
CALLER_FEE = Decimal("16.75")
OTHER_FEE = Decimal("99.99")


def _in_session(fn):
    token = db.open_session()
    try:
        return fn()
    finally:
        db.close_session(token)


def _stub_rate(monkeypatch, *, rate=Decimal("18.50")):
    monkeypatch.setattr(
        "remitx_api.controllers.stokvel_controller.token_rates",
        lambda currency: TokenRates(
            currency=currency,
            units_per_token=rate,
            token_per_unit=Decimal("1") / rate,
            zar_token_per_unit=Decimal("1") / rate,
        ),
    )


def _body():
    return {"name": "Family", "currency": "ZAR", "contribution_amount": "25"}


def test_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.get(f"{STOKVELS}/{uuid.uuid4()}")

    assert response.status_code == 401


def test_member_sees_a_forming_stokvel(verified_client, monkeypatch):
    _stub_rate(monkeypatch)
    client, _user = verified_client
    created = client.post(STOKVELS, json=_body())
    assert created.status_code == 201, created.text
    stokvel_id = created.json()["stokvel_id"]

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stokvel_id"] == stokvel_id
    assert body["phase"] == "forming"
    assert body["contribution_fiat_estimate"] == "462.50"
    assert body["organiser_name"] == "Verified"
    assert body["current_round"] is None
    assert body["total_rounds"] is None
    assert body["next_payout_time"] is None
    assert body["my_contribution_status"] is None
    assert body["my_beneficiary"] is None
    assert body["contributions"] == []
    assert body["invitations"] == []
    assert len(body["members"]) == 1
    member = body["members"][0]
    assert member["member_id"] == body["my_member_id"]
    assert member["is_me"] is True
    assert member["is_organiser"] is True
    assert member["full_name"] == "Verified"
    cycle = body["cycle"]
    assert cycle["status"] == "forming"
    assert cycle["cycle_number"] == 1
    assert cycle["rounds"] == []
    assert cycle["payout_order"] == []
    assert cycle["registered_at"] is None
    assert "remittance_reference" not in response.text


def test_a_missing_rate_leaves_the_estimate_empty(verified_client, monkeypatch):
    def unavailable(currency):
        raise RateUnavailableError(currency)

    monkeypatch.setattr(
        "remitx_api.controllers.stokvel_controller.token_rates", unavailable
    )
    client, _user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = created.json()["stokvel_id"]

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    assert response.json()["contribution_fiat_estimate"] is None


def test_unknown_and_non_member_are_not_found(verified_client, monkeypatch):
    _stub_rate(monkeypatch)
    client, _user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = created.json()["stokvel_id"]

    missing = client.get(f"{STOKVELS}/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Stokvel not found."

    other_id = _in_session(
        lambda: (
            UserController()
            .ensure_provisioned(
                "user_stokvel_outsider",
                lambda: "outsider@example.com",
                lambda: "Outsider",
            )
            .id
        )
    )
    client.app.dependency_overrides[get_current_user] = lambda: User(id=other_id)
    hidden = client.get(f"{STOKVELS}/{stokvel_id}")
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "Stokvel not found."


def test_fee_is_only_the_callers_and_a_payout_waits_for_its_remittance(
    verified_client, monkeypatch
):
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    caller_member_id, other_member_id = _activate(stokvel_id, user.id)

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "active"
    assert body["current_round"] == 0
    assert body["my_contribution_status"] == "pending"
    assert body["next_payout_time"] == "2026-11-03T00:00:00+00:00"
    assert body["cycle"]["payout_order"] == [caller_member_id, other_member_id]
    assert body["cycle"]["registered_at"] is None
    fees = {row["member_id"]: row["fee_amount"] for row in body["contributions"]}
    assert fees[caller_member_id] == "16.75"
    assert fees[other_member_id] is None
    rnd = body["cycle"]["rounds"][0]
    assert rnd["release_status"] == "pending"
    assert rnd["remittance_status"] is None
    assert rnd["remittance_id"] is None
    assert rnd["pool_fiat_amount"] is None
    assert rnd["recipient_member_id"] == caller_member_id
    assert "remittance_reference" not in rnd


def _activate(stokvel_id: uuid.UUID, organiser_id: uuid.UUID):
    """Turn the new forming cycle into an active one-round payout with two
    contributions. The other member's fee leg exists, and must not be returned."""

    def write():
        stokvel = db.session.get(Stokvel, stokvel_id)
        cycle = db.session.get(StokvelCycle, stokvel.current_cycle_id)
        organiser = db.session.scalars(
            select(StokvelMember).where(StokvelMember.user_id == organiser_id)
        ).one()
        other = UserController().ensure_provisioned(
            "user_stokvel_other",
            lambda: "other-member@example.com",
            lambda: "Sipho",
        )
        other_account = AccountRepository().get_user_account(other.id, CURRENCY_ZAR)
        organiser_account = AccountRepository().get_user_account(
            organiser_id, CURRENCY_ZAR
        )
        other_member = StokvelMember(
            stokvel_id=stokvel.id,
            user_id=other.id,
            account_id=other_account.account_id,
        )
        db.session.add(other_member)
        db.session.flush()
        cycle.status = StokvelCycleStatus.ACTIVE.value
        cycle.started_at = datetime.now(UTC)
        cycle.total_rounds = 2
        cycle.current_round = 0
        organiser_place = db.session.get(StokvelCycleMember, (cycle.id, organiser.id))
        organiser_place.payout_position = 0
        db.session.add(
            StokvelCycleMember(
                cycle_id=cycle.id,
                member_id=other_member.id,
                payout_position=1,
            )
        )
        for number, day in ((0, PAYOUT_TIME), (1, PAYOUT_TIME + timedelta(weeks=1))):
            db.session.add(
                StokvelRound(
                    cycle_id=cycle.id,
                    round=number,
                    start_time=day - timedelta(days=2),
                    deadline=day - timedelta(days=1),
                    payout_time=day,
                )
            )
        caller_fee = _fee(
            organiser_account.account_id, other_account.account_id, CALLER_FEE
        )
        other_fee = _fee(
            other_account.account_id, organiser_account.account_id, OTHER_FEE
        )
        db.session.add(
            StokvelContribution(
                cycle_id=cycle.id,
                round=0,
                member_id=organiser.id,
                amount_token=Decimal("25"),
                amount_fiat=Decimal("462.50"),
                status=StokvelContributionStatus.PENDING.value,
                fee_tx_id=caller_fee.tx_id,
            )
        )
        db.session.add(
            StokvelContribution(
                cycle_id=cycle.id,
                round=0,
                member_id=other_member.id,
                amount_token=Decimal("25"),
                amount_fiat=Decimal("462.50"),
                status=StokvelContributionStatus.CONFIRMED.value,
                fee_tx_id=other_fee.tx_id,
                evm_tx_hash="0xabc",
                block_number=1,
                confirmed_at=datetime.now(UTC),
            )
        )
        db.session.add(
            StokvelPayout(
                cycle_id=cycle.id,
                round=0,
                member_id=organiser.id,
                release_status=StokvelPayoutReleaseStatus.PENDING.value,
                remittance_status="pending",
            )
        )
        db.session.commit()
        return str(organiser.id), str(other_member.id)

    return _in_session(write)


def _fee(credit_account_id, debit_account_id, amount: Decimal) -> Transaction:
    fee = Transaction(
        type=TYPE_FEE,
        credit_account_id=credit_account_id,
        debit_account_id=debit_account_id,
        amount=amount,
        currency=CURRENCY_ZAR,
        status="pending",
    )
    db.session.add(fee)
    db.session.flush()
    return fee
