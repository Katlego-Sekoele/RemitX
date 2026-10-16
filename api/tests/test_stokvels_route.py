"""`POST /stokvels` and `GET /stokvels` (R2-07) on SQLite, which has no
row-level security: the scoping tests here prove the controller filters by
the caller itself. The same reads under Postgres row-level security are in
`test_stokvels_row_security.py`."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_USD,
    CURRENCY_ZAR,
    TYPE_STOKVEL,
    Account,
)
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.routes import stokvels as stokvels_route
from sqlalchemy import select
from tests.kyc_helpers import seed_kyc_reference_data

STOKVELS = "/stokvels"
ACCOUNTS = "/accounts"
MAX_MEMBERS = TestConfig().MAX_STOKVEL_MEMBERS


def _body(**overrides) -> dict:
    return {
        "name": "Family",
        "currency": "ZAR",
        "contribution_amount": "25",
        **overrides,
    }


def _in_session(fn):
    """Run `fn` in a session of its own, outside any request."""
    token = db.open_session()
    try:
        return fn()
    finally:
        db.close_session(token)


def _rows():
    """(stokvels, members, STOKVEL accounts) currently stored."""
    return _in_session(
        lambda: (
            db.session.scalars(select(Stokvel)).all(),
            db.session.scalars(select(StokvelMember)).all(),
            db.session.scalars(
                select(Account).where(Account.type == TYPE_STOKVEL)
            ).all(),
        )
    )


def _provision_user(clerk_id: str, last_name: str | None = None) -> uuid.UUID:
    """A persisted user with their sign-up ZAR and token accounts."""

    def provision():
        user = UserController().ensure_provisioned(
            clerk_id, lambda: f"{clerk_id}@example.com", lambda: "Other"
        )
        user.last_name = last_name
        db.session.commit()
        return user.id

    return _in_session(provision)


def _sign_in_as(client, user_id: uuid.UUID) -> None:
    user = User(id=user_id)
    client.app.dependency_overrides[get_current_user] = lambda: user


def _insert_stokvel(
    organiser_id: uuid.UUID,
    name: str,
    *,
    created_at: datetime | None = None,
    deactivated_at: datetime | None = None,
) -> uuid.UUID:
    """A stokvel and its Organiser's membership, written directly."""

    def insert():
        stokvel = Stokvel(
            organiser_user_id=organiser_id,
            name=name,
            currency=CURRENCY_ZAR,
            contribution_amount=Decimal("10"),
            created_at=created_at or datetime.now(UTC),
            deactivated_at=deactivated_at,
        )
        db.session.add(stokvel)
        db.session.flush()
        _add_member(stokvel.id, organiser_id)
        db.session.commit()
        return stokvel.id

    return _in_session(insert)


def _add_member(stokvel_id, user_id, **columns) -> None:
    account = AccountRepository().get_user_account(user_id, CURRENCY_ZAR)
    db.session.add(
        StokvelMember(
            stokvel_id=stokvel_id,
            user_id=user_id,
            account_id=account.account_id,
            **columns,
        )
    )
    db.session.flush()


def _join(stokvel_id, user_id, *, left: bool = False) -> None:
    """`user_id` joins by an accepted invitation (and has left, if `left`)."""

    def join():
        stokvel = db.session.get(Stokvel, stokvel_id)
        invitation = _invitation(
            stokvel, user_id, StokvelInvitationStatus.ACCEPTED, by=user_id
        )
        _add_member(
            stokvel_id,
            user_id,
            invitation_id=invitation.id,
            left_at=datetime.now(UTC) if left else None,
        )
        db.session.commit()

    _in_session(join)


def _invitation(stokvel, invitee_id, status, *, by=None, created_at=None):
    changed = status != StokvelInvitationStatus.PENDING
    invitation = StokvelInvitation(
        stokvel_id=stokvel.id,
        invitee_user_id=invitee_id,
        invited_by_user_id=stokvel.organiser_user_id,
        status=status.value,
        created_at=created_at or datetime.now(UTC),
        status_changed_at=datetime.now(UTC) if changed else None,
        status_changed_by_user_id=(by or stokvel.organiser_user_id)
        if changed
        else None,
    )
    db.session.add(invitation)
    db.session.flush()
    return invitation


def _invite(stokvel_id, invitee_id, status=StokvelInvitationStatus.PENDING, **kw):
    def invite():
        stokvel = db.session.get(Stokvel, stokvel_id)
        invitation = _invitation(stokvel, invitee_id, status, **kw)
        db.session.commit()
        return invitation.id

    return _in_session(invite)


# --- create -----------------------------------------------------------------


def test_create_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(STOKVELS, json=_body())

    assert response.status_code == 401


def test_list_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.get(STOKVELS)

    assert response.status_code == 401


def test_create_requires_kyc_verification(client):
    _in_session(seed_kyc_reference_data)

    response = client.post(STOKVELS, json=_body())

    assert response.status_code == 403
    assert "verified" in response.json()["detail"].lower()
    assert _rows() == ([], [], [])


def test_create_makes_the_caller_organiser_and_first_member(verified_client):
    client, user = verified_client

    response = client.post(STOKVELS, json=_body(contribution_amount="25.5"))

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Family"
    assert body["currency"] == "ZAR"
    assert body["contribution_amount"] == "25.50000000"
    assert body["is_organiser"] is True
    assert body["member_count"] == 1
    assert body["max_members"] == MAX_MEMBERS
    assert body["deactivated_at"] is None
    assert body["created_at"].endswith("+00:00")

    stokvels, members, stokvel_accounts = _rows()
    assert len(stokvels) == 1
    stokvel = stokvels[0]
    assert str(stokvel.id) == body["stokvel_id"]
    assert stokvel.organiser_user_id == user.id
    assert stokvel.contribution_amount == Decimal("25.5")

    zar = _in_session(
        lambda: AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    )
    assert len(members) == 1
    member = members[0]
    assert member.stokvel_id == stokvel.id
    assert member.user_id == user.id
    assert member.account_id == zar.account_id
    assert member.invitation_id is None
    assert member.left_at is None

    assert len(stokvel_accounts) == 1
    ledger = stokvel_accounts[0]
    assert stokvel.account_id == ledger.account_id
    assert ledger.account_currency == CURRENCY_TOKEN
    assert ledger.label == f"Stokvel {stokvel.id}"
    assert ledger.user_id is None
    assert ledger.account_balance == 0


def test_create_reads_back_the_same_through_the_list(verified_client):
    client, _user = verified_client

    created = client.post(STOKVELS, json=_body()).json()
    listed = client.get(STOKVELS).json()

    assert listed == {"stokvels": [created], "invitations": []}


def test_create_needs_an_account_in_the_stokvel_currency(verified_client):
    client, _user = verified_client

    response = client.post(STOKVELS, json=_body(currency="USD"))

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Open a USD account first. Your contributions are paid from it."
    )
    assert _rows() == ([], [], [])


def test_create_uses_the_callers_account_in_the_stokvel_currency(verified_client):
    client, user = verified_client
    assert client.post(ACCOUNTS, json={"currency": "USD"}).status_code == 201

    response = client.post(STOKVELS, json=_body(currency="USD"))

    assert response.status_code == 201
    assert response.json()["currency"] == "USD"
    usd = _in_session(
        lambda: AccountRepository().get_user_account(user.id, CURRENCY_USD)
    )
    _stokvels, members, _accounts = _rows()
    assert [member.account_id for member in members] == [usd.account_id]


def test_create_writes_nothing_if_any_step_fails(verified_client, monkeypatch):
    client, _user = verified_client

    def fail(_member):
        raise RuntimeError("membership insert failed")

    monkeypatch.setattr(stokvels_route.controller._members, "add", fail)

    with pytest.raises(RuntimeError, match="membership insert failed"):
        client.post(STOKVELS, json=_body())

    assert _rows() == ([], [], [])


def test_create_strips_the_name(verified_client):
    client, _user = verified_client

    response = client.post(STOKVELS, json=_body(name="  Family  "))

    assert response.status_code == 201
    assert response.json()["name"] == "Family"


def test_two_stokvels_may_share_a_name(verified_client):
    client, _user = verified_client

    first = client.post(STOKVELS, json=_body())
    second = client.post(STOKVELS, json=_body())

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["stokvel_id"] != second.json()["stokvel_id"]


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": TestConfig().UCTUSD_TOKEN_NAME},
        {"currency": "EUR"},
        {"currency": None},
        {"contribution_amount": "0"},
        {"contribution_amount": "-1"},
        {"contribution_amount": "0.000000001"},
        {"contribution_amount": "1" * 21},
        {"contribution_amount": "abc"},
        {"contribution_amount": None},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 81},
        {"name": None},
        {"stokvel_id": str(uuid.uuid4())},
    ],
    ids=lambda changes: ",".join(f"{k}={str(v)[:12]}" for k, v in changes.items()),
)
def test_create_rejects_invalid_input(verified_client, changes):
    client, _user = verified_client
    body = _body(**changes)
    for field, value in changes.items():
        if value is None:
            del body[field]

    response = client.post(STOKVELS, json=body)

    assert response.status_code == 422
    assert _rows() == ([], [], [])


def test_create_accepts_the_longest_name(verified_client):
    client, _user = verified_client

    response = client.post(STOKVELS, json=_body(name="x" * 80))

    assert response.status_code == 201


# --- list -------------------------------------------------------------------


def test_list_is_empty_for_a_new_user(verified_client):
    client, _user = verified_client

    response = client.get(STOKVELS)

    assert response.status_code == 200
    assert response.json() == {"stokvels": [], "invitations": []}


def test_list_shows_the_callers_stokvels_newest_first(verified_client):
    client, user = verified_client
    now = datetime.now(UTC)
    older = _insert_stokvel(user.id, "Older", created_at=now - timedelta(days=1))
    newer = _insert_stokvel(user.id, "Newer", created_at=now)

    stokvels = client.get(STOKVELS).json()["stokvels"]

    assert [s["stokvel_id"] for s in stokvels] == [str(newer), str(older)]
    assert all(s["is_organiser"] for s in stokvels)


def test_list_shows_a_stokvel_joined_by_invitation(verified_client):
    client, user = verified_client
    organiser = _provision_user("organiser_joined")
    stokvel_id = _insert_stokvel(organiser, "Theirs")
    _join(stokvel_id, user.id)

    stokvels = client.get(STOKVELS).json()["stokvels"]

    assert len(stokvels) == 1
    assert stokvels[0]["stokvel_id"] == str(stokvel_id)
    assert stokvels[0]["is_organiser"] is False
    assert stokvels[0]["member_count"] == 2


def test_list_member_count_leaves_out_former_members(verified_client):
    client, user = verified_client
    stokvel_id = _insert_stokvel(user.id, "Ours")
    _join(stokvel_id, _provision_user("current_member"))
    _join(stokvel_id, _provision_user("former_member"), left=True)

    stokvels = client.get(STOKVELS).json()["stokvels"]

    assert stokvels[0]["member_count"] == 2


def test_list_leaves_out_other_users_stokvels(verified_client):
    """SQLite has no row-level security: only the controller's own
    filtering keeps another user's stokvel out."""
    client, user = verified_client
    _insert_stokvel(_provision_user("stranger"), "Not yours")
    mine = _insert_stokvel(user.id, "Mine")

    stokvels = client.get(STOKVELS).json()["stokvels"]

    assert [s["stokvel_id"] for s in stokvels] == [str(mine)]


def test_list_leaves_out_a_stokvel_the_caller_has_left(verified_client):
    client, user = verified_client
    stokvel_id = _insert_stokvel(_provision_user("left_organiser"), "Left")
    _join(stokvel_id, user.id, left=True)

    assert client.get(STOKVELS).json()["stokvels"] == []


def test_list_keeps_a_deactivated_stokvel_with_its_date(verified_client):
    client, user = verified_client
    _insert_stokvel(user.id, "Retired", deactivated_at=datetime.now(UTC))

    stokvels = client.get(STOKVELS).json()["stokvels"]

    assert len(stokvels) == 1
    assert stokvels[0]["deactivated_at"] is not None


def test_list_shows_pending_invitations_newest_first(verified_client):
    client, user = verified_client
    organiser = _provision_user("inviting_organiser", last_name="Moyo")
    first = _insert_stokvel(organiser, "First")
    second = _insert_stokvel(organiser, "Second")
    now = datetime.now(UTC)
    older = _invite(first, user.id, created_at=now - timedelta(hours=1))
    newer = _invite(second, user.id, created_at=now)

    body = client.get(STOKVELS).json()

    assert body["stokvels"] == []
    assert [i["invitation_id"] for i in body["invitations"]] == [
        str(newer),
        str(older),
    ]
    invitation = body["invitations"][0]
    assert invitation["stokvel_id"] == str(second)
    assert invitation["stokvel_name"] == "Second"
    assert invitation["currency"] == "ZAR"
    assert invitation["contribution_amount"] == "10.00000000"
    assert invitation["invited_by_name"] == "Other M."


@pytest.mark.parametrize(
    "status",
    [
        StokvelInvitationStatus.DECLINED,
        StokvelInvitationStatus.REVOKED,
        StokvelInvitationStatus.LAPSED,
    ],
)
def test_list_leaves_out_answered_invitations(verified_client, status):
    client, user = verified_client
    stokvel_id = _insert_stokvel(_provision_user(f"org_{status.value}"), "Answered")
    by = user.id if status == StokvelInvitationStatus.DECLINED else None
    _invite(stokvel_id, user.id, status, by=by)

    assert client.get(STOKVELS).json() == {"stokvels": [], "invitations": []}


def test_list_leaves_out_invitations_to_someone_else(verified_client):
    client, _user = verified_client
    stokvel_id = _insert_stokvel(_provision_user("other_org"), "Not for you")
    _invite(stokvel_id, _provision_user("other_invitee"))

    assert client.get(STOKVELS).json()["invitations"] == []


def test_an_accepted_invitation_lists_as_a_stokvel(verified_client):
    client, user = verified_client
    stokvel_id = _insert_stokvel(_provision_user("accepting_org"), "Joined")
    _join(stokvel_id, user.id)

    body = client.get(STOKVELS).json()

    assert [s["stokvel_id"] for s in body["stokvels"]] == [str(stokvel_id)]
    assert body["invitations"] == []


def test_a_new_member_sees_the_stokvel_after_sign_in(verified_client):
    """The Organiser creates through the API; another user who joins sees
    it, and an outsider does not."""
    client, _organiser = verified_client
    stokvel_id = client.post(STOKVELS, json=_body()).json()["stokvel_id"]
    member = _provision_user("api_member")
    outsider = _provision_user("api_outsider")
    _join(uuid.UUID(stokvel_id), member)

    _sign_in_as(client, member)
    as_member = client.get(STOKVELS).json()["stokvels"]
    _sign_in_as(client, outsider)
    as_outsider = client.get(STOKVELS).json()["stokvels"]

    assert [s["stokvel_id"] for s in as_member] == [stokvel_id]
    assert as_member[0]["is_organiser"] is False
    assert as_member[0]["member_count"] == 2
    assert as_outsider == []
