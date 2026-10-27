"""`GET /stokvels/{id}` (R2-14, #236) on SQLite, which has no row-level security.
The controller scopes by the caller itself."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.auth.dependencies import get_current_user
from remitx_api.controllers.stokvel_cycle_controller import open_next_cycle
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EVM_WALLET,
    Account,
    create_account_reference,
)
from remitx_api.models.orm.beneficiary import Beneficiary, BeneficiaryRelationship
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_payout import (
    StokvelPayout,
    StokvelPayoutReleaseStatus,
)
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.models.orm.transaction import (
    TYPE_FEE,
    TYPE_STOKVEL_POOL_RELEASE,
    Transaction,
    TransactionStatus,
)
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.stokvel_contribution_repository import (
    StokvelContributionRepository,
)
from remitx_api.services.exchange_rate_service import RateUnavailableError
from remitx_api.services.quote_service import TokenRates
from sqlalchemy import select
from tests.send_helpers import record_transfer

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
    assert body["open_round"] is None
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
    assert body["previous_cycle"] is None
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


def test_current_round_stays_the_stored_column_when_the_open_round_moves(
    verified_client, monkeypatch
):
    """`current_round` is the column set at start. `open_round` is the round
    a contribution goes into, and it moves once a round is full. The contract
    advances its round cursor on release (`nextToFinalise`), which is not
    this read."""
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    _activate(stokvel_id, user.id)
    opened = _in_session(
        lambda: _open_round(stokvel_id),
    )

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert opened == 1
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_round"] == 0
    assert body["cycle"]["current_round"] == 0
    assert body["open_round"] == 1
    assert body["my_contribution_status"] == "pending"
    assert body["next_payout_time"] == "2026-11-03T00:00:00+00:00"


def test_only_the_organiser_sees_an_invitee_reference(verified_client, monkeypatch):
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    member_id, reference = _pending_invitation(stokvel_id, user.id)

    as_organiser = client.get(f"{STOKVELS}/{stokvel_id}")

    assert as_organiser.status_code == 200, as_organiser.text
    invitation = as_organiser.json()["invitations"][0]
    assert invitation["account_reference"] == reference
    assert invitation["invitee_name"] == "Thandi"

    client.app.dependency_overrides[get_current_user] = lambda: User(id=member_id)
    as_member = client.get(f"{STOKVELS}/{stokvel_id}")

    assert as_member.status_code == 200, as_member.text
    hidden = as_member.json()["invitations"][0]
    assert hidden["invitation_id"] == invitation["invitation_id"]
    assert hidden["account_reference"] is None
    assert hidden["invitee_name"] == "Thandi"


def test_every_invitation_is_returned_whatever_its_status(verified_client, monkeypatch):
    """Members see answered invitations too (#299, R2-17), newest first."""
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    _member_id, invitations = _invitation_of_each_status(stokvel_id, user.id)

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    returned = [
        (row["invitation_id"], row["status"]) for row in response.json()["invitations"]
    ]
    assert returned == [
        (str(invitation_id), status)
        for status, (invitation_id, _reference) in reversed(invitations.items())
    ]


def test_only_the_organiser_sees_the_reference_on_an_answered_invitation(
    verified_client, monkeypatch
):
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    member_id, invitations = _invitation_of_each_status(stokvel_id, user.id)
    invitation_id, reference = invitations["declined"]

    def declined(response):
        assert response.status_code == 200, response.text
        (row,) = [
            row
            for row in response.json()["invitations"]
            if row["invitation_id"] == str(invitation_id)
        ]
        assert row["status"] == "declined"
        return row

    as_organiser = declined(client.get(f"{STOKVELS}/{stokvel_id}"))
    client.app.dependency_overrides[get_current_user] = lambda: User(id=member_id)
    as_member = declined(client.get(f"{STOKVELS}/{stokvel_id}"))

    assert as_organiser["account_reference"] == reference
    assert as_member["account_reference"] is None


def test_payout_order_ignores_an_unlocked_former_member(verified_client, monkeypatch):
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    caller_member_id, other_member_id = _activate(stokvel_id, user.id)
    _stale_cycle_row(stokvel_id)

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    assert response.json()["cycle"]["payout_order"] == [
        caller_member_id,
        other_member_id,
    ]


def test_payout_order_keeps_a_locked_member_who_left_mid_cycle(
    verified_client, monkeypatch
):
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    caller_member_id, other_member_id = _activate(stokvel_id, user.id)
    leaver_id = _locked_leaver(stokvel_id, user.id)

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    assert response.json()["cycle"]["payout_order"] == [
        caller_member_id,
        other_member_id,
        leaver_id,
    ]


def test_a_gap_in_the_payout_order_has_no_recipient(verified_client, monkeypatch):
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    first = _gap(stokvel_id, user.id)

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    cycle = response.json()["cycle"]
    assert cycle["payout_order"] == [first]
    recipients = {row["round"]: row["recipient_member_id"] for row in cycle["rounds"]}
    assert recipients == {0: first, 1: None, 2: None}


def test_a_sent_payout_returns_its_remittance_status(verified_client, monkeypatch):
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    _activate(stokvel_id, user.id)
    remittance_id = _attach_remittance(stokvel_id)

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    rnd = response.json()["cycle"]["rounds"][0]
    assert rnd["remittance_id"] == remittance_id
    assert rnd["remittance_status"] == "processing"
    assert rnd["release_status"] == "released"


def test_a_closed_cycle_stays_on_the_screen_while_the_next_is_forming(
    verified_client, monkeypatch
):
    """Brief §2 step 6: each round's release status, hashes and remittance
    stay visible after the worker opens cycle 2 (R2-15, #237)."""
    _stub_rate(monkeypatch)
    client, user = verified_client
    created = client.post(STOKVELS, json=_body())
    stokvel_id = uuid.UUID(created.json()["stokvel_id"])
    organiser_member, other_member = _activate(stokvel_id, user.id)
    remittance_id = _attach_remittance(stokvel_id)
    closed_id = _close_and_open_next(stokvel_id)

    response = client.get(f"{STOKVELS}/{stokvel_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "forming"
    assert body["cycle"]["cycle_number"] == 2
    assert body["cycle"]["rounds"] == []
    previous = body["previous_cycle"]
    assert previous["cycle_id"] == closed_id
    assert previous["cycle_number"] == 1
    assert previous["status"] == "closed"
    assert previous["closed_at"] is not None
    assert previous["payout_order"] == [organiser_member, other_member]
    first = previous["rounds"][0]
    assert first["recipient_member_id"] == organiser_member
    assert first["release_status"] == "released"
    assert first["release_tx_hash"] == "0xrelease"
    assert first["remittance_id"] == remittance_id
    assert first["remittance_status"] == "processing"


def _close_and_open_next(stokvel_id: uuid.UUID) -> str:
    """Close the current cycle and open the next, as the worker does on
    `CycleClosed`."""

    def write():
        stokvel = db.session.get(Stokvel, stokvel_id)
        cycle = db.session.get(StokvelCycle, stokvel.current_cycle_id)
        cycle.status = StokvelCycleStatus.CLOSED.value
        cycle.closed_at = datetime.now(UTC)
        db.session.flush()
        open_next_cycle(db.session, cycle)
        db.session.commit()
        return str(cycle.id)

    return _in_session(write)


def _locked_leaver(stokvel_id: uuid.UUID, organiser_id: uuid.UUID) -> str:
    """A locked cycle row for someone who left mid-cycle; they stay in the order."""

    def write():
        stokvel = db.session.get(Stokvel, stokvel_id)
        cycle = db.session.get(StokvelCycle, stokvel.current_cycle_id)
        organiser = db.session.scalars(
            select(StokvelMember).where(StokvelMember.user_id == organiser_id)
        ).one()
        leaver = UserController().ensure_provisioned(
            "user_stokvel_leaver",
            lambda: "leaver@example.com",
            lambda: "Leaver",
        )
        account = AccountRepository().get_user_account(leaver.id, CURRENCY_ZAR)
        member = StokvelMember(
            stokvel_id=stokvel.id,
            user_id=leaver.id,
            account_id=account.account_id,
            left_at=datetime.now(UTC),
        )
        db.session.add(member)
        db.session.flush()
        beneficiary = Beneficiary(
            sender_user_id=leaver.id,
            linked_user_id=organiser.user_id,
            payout_currency=CURRENCY_ZAR,
            relationship=BeneficiaryRelationship.PARENT.value,
        )
        db.session.add(beneficiary)
        db.session.flush()
        db.session.add(
            StokvelCycleMember(
                cycle_id=cycle.id,
                member_id=member.id,
                payout_position=2,
                payout_beneficiary_id=beneficiary.beneficiary_id,
                payout_currency=CURRENCY_ZAR,
                locked=True,
            )
        )
        db.session.commit()
        return str(member.id)

    return _in_session(write)


def _stale_cycle_row(stokvel_id: uuid.UUID) -> None:
    """An unlocked cycle row with a position, for someone no longer a member."""

    def write():
        stokvel = db.session.get(Stokvel, stokvel_id)
        cycle = db.session.get(StokvelCycle, stokvel.current_cycle_id)
        former = UserController().ensure_provisioned(
            "user_stokvel_former",
            lambda: "former@example.com",
            lambda: "Former",
        )
        account = AccountRepository().get_user_account(former.id, CURRENCY_ZAR)
        former_member = StokvelMember(
            stokvel_id=stokvel.id,
            user_id=former.id,
            account_id=account.account_id,
            left_at=datetime.now(UTC),
        )
        db.session.add(former_member)
        db.session.flush()
        db.session.add(
            StokvelCycleMember(
                cycle_id=cycle.id,
                member_id=former_member.id,
                payout_position=2,
                locked=False,
            )
        )
        db.session.commit()

    _in_session(write)


def _open_round(stokvel_id: uuid.UUID) -> int | None:
    stokvel = db.session.get(Stokvel, stokvel_id)
    cycle = db.session.get(StokvelCycle, stokvel.current_cycle_id)
    return StokvelContributionRepository().open_round(
        cycle.id, member_count=2, total_rounds=cycle.total_rounds
    )


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


def _pending_invitation(stokvel_id: uuid.UUID, organiser_id: uuid.UUID):
    """A second current member, and a pending invitation to someone else."""

    def write():
        member = UserController().ensure_provisioned(
            "user_stokvel_reader",
            lambda: "reader@example.com",
            lambda: "Reader",
        )
        invitee = UserController().ensure_provisioned(
            "user_stokvel_invitee",
            lambda: "invitee@example.com",
            lambda: "Thandi",
        )
        account = AccountRepository().get_user_account(member.id, CURRENCY_ZAR)
        db.session.add(
            StokvelMember(
                stokvel_id=stokvel_id,
                user_id=member.id,
                account_id=account.account_id,
            )
        )
        db.session.add(
            StokvelInvitation(
                stokvel_id=stokvel_id,
                invitee_user_id=invitee.id,
                invited_by_user_id=organiser_id,
                status="pending",
            )
        )
        db.session.commit()
        return member.id, create_account_reference(invitee.base_reference, CURRENCY_ZAR)

    return _in_session(write)


def _invitation_of_each_status(stokvel_id: uuid.UUID, organiser_id: uuid.UUID):
    """A second current member, and one invitation of each status to someone
    else, each a day newer than the last. The member's id, and each status's
    invitation id and invitee reference, oldest first."""

    def write():
        member = UserController().ensure_provisioned(
            "user_stokvel_reader",
            lambda: "reader@example.com",
            lambda: "Reader",
        )
        account = AccountRepository().get_user_account(member.id, CURRENCY_ZAR)
        db.session.add(
            StokvelMember(
                stokvel_id=stokvel_id,
                user_id=member.id,
                account_id=account.account_id,
            )
        )
        invitations = {}
        start = datetime(2026, 10, 1, tzinfo=UTC)
        for day, status in enumerate(StokvelInvitationStatus):
            invitee = UserController().ensure_provisioned(
                f"user_stokvel_{status}",
                lambda status=status: f"{status}@example.com",
                lambda: "Thandi",
            )
            answered = status != StokvelInvitationStatus.PENDING
            by_invitee = status in (
                StokvelInvitationStatus.ACCEPTED,
                StokvelInvitationStatus.DECLINED,
            )
            invitation = StokvelInvitation(
                stokvel_id=stokvel_id,
                invitee_user_id=invitee.id,
                invited_by_user_id=organiser_id,
                status=status.value,
                created_at=start + timedelta(days=day),
                status_changed_at=start + timedelta(days=day, hours=1)
                if answered
                else None,
                status_changed_by_user_id=(
                    None if not answered else invitee.id if by_invitee else organiser_id
                ),
            )
            db.session.add(invitation)
            db.session.flush()
            invitations[status.value] = (
                invitation.id,
                create_account_reference(invitee.base_reference, CURRENCY_ZAR),
            )
        db.session.commit()
        return member.id, invitations

    return _in_session(write)


def _gap(stokvel_id: uuid.UUID, organiser_id: uuid.UUID) -> str:
    """Positions 0 and 2, so the order stops before round 1."""

    def write():
        stokvel = db.session.get(Stokvel, stokvel_id)
        cycle = db.session.get(StokvelCycle, stokvel.current_cycle_id)
        organiser = db.session.scalars(
            select(StokvelMember).where(StokvelMember.user_id == organiser_id)
        ).one()
        other = UserController().ensure_provisioned(
            "user_stokvel_gap",
            lambda: "gap-member@example.com",
            lambda: "Gap",
        )
        other_account = AccountRepository().get_user_account(other.id, CURRENCY_ZAR)
        other_member = StokvelMember(
            stokvel_id=stokvel.id,
            user_id=other.id,
            account_id=other_account.account_id,
        )
        db.session.add(other_member)
        db.session.flush()
        cycle.status = StokvelCycleStatus.ACTIVE.value
        cycle.started_at = datetime.now(UTC)
        cycle.total_rounds = 3
        cycle.current_round = 0
        organiser_place = db.session.get(StokvelCycleMember, (cycle.id, organiser.id))
        organiser_place.payout_position = 0
        db.session.add(
            StokvelCycleMember(
                cycle_id=cycle.id,
                member_id=other_member.id,
                payout_position=2,
            )
        )
        for number in range(3):
            day = PAYOUT_TIME + timedelta(weeks=number)
            db.session.add(
                StokvelRound(
                    cycle_id=cycle.id,
                    round=number,
                    start_time=day - timedelta(days=2),
                    deadline=day - timedelta(days=1),
                    payout_time=day,
                )
            )
        db.session.commit()
        return str(organiser.id)

    return _in_session(write)


def _attach_remittance(stokvel_id: uuid.UUID) -> str:
    """Release round 0's payout and attach a remittance still sending."""

    def write():
        stokvel = db.session.get(Stokvel, stokvel_id)
        cycle = db.session.get(StokvelCycle, stokvel.current_cycle_id)
        payout = db.session.scalars(
            select(StokvelPayout).where(StokvelPayout.cycle_id == cycle.id)
        ).one()
        organiser = db.session.get(User, stokvel.organiser_user_id)
        remittance = record_transfer(stokvel, organiser, sender_amount=Decimal("925"))
        accounts = AccountRepository()
        treasury = accounts.get_platform_account(TYPE_EVM_WALLET, CURRENCY_TOKEN)
        if treasury is None:
            treasury = Account(
                user_id=None,
                type=TYPE_EVM_WALLET,
                account_currency=CURRENCY_TOKEN,
                label="member-view treasury",
            )
            db.session.add(treasury)
            db.session.flush()
        leg = Transaction(
            type=TYPE_STOKVEL_POOL_RELEASE,
            credit_account_id=accounts.get_stokvel_account(stokvel.id).account_id,
            debit_account_id=treasury.account_id,
            amount=Decimal("50"),
            currency=CURRENCY_TOKEN,
            status="confirmed",
        )
        db.session.add(leg)
        db.session.flush()
        payout.release_status = "released"
        payout.release_tx_hash = "0xrelease"
        payout.release_block_number = 1
        payout.release_tx_id = leg.tx_id
        payout.released_at = datetime.now(UTC)
        payout.remittance_status = TransactionStatus.PROCESSING.value
        payout.quote_id = remittance.quote_id
        payout.remittance_id = remittance.remittance_id
        db.session.commit()
        return str(remittance.remittance_id)

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
