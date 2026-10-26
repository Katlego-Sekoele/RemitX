"""`POST /stokvels/{id}/invitations`, `POST /invitations/{id}/accept`,
`POST /invitations/{id}/decline` (R2-08) and `POST /invitations/{id}/revoke`
(R2-16).

On SQLite, which has no row-level security, except the tests marked
`postgres`, which run the same routes under it (TEST_DATABASE_URL): the
invitee's KYC check, the member cap from an invitee's side and two accepts
racing for the last place. The database's own membership rules are in
`test_stokvel_member_row_security.py`.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_USD,
    CURRENCY_ZAR,
    create_account_reference,
)
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.routes import stokvel_invitations as invitations_route
from sqlalchemy import select
from tests.kyc_helpers import insert_application, seed_kyc_reference_data

MAX_MEMBERS = TestConfig().MAX_STOKVEL_MEMBERS
# Picks the caller per request, so threads can call as different users.
USER_HEADER = "X-Test-User"


def _in_session(fn):
    """Run `fn` in a session of its own, outside any request."""
    token = db.open_session()
    try:
        return fn()
    finally:
        db.close_session(token)


@dataclass(frozen=True)
class Person:
    id: uuid.UUID
    base_reference: str

    def ref(self, currency: str = CURRENCY_ZAR) -> str:
        return create_account_reference(self.base_reference, currency)


def _person(
    name: str = "thandi", *, verified: bool = True, last_name: str | None = None
) -> Person:
    """A user with their sign-up ZAR and token accounts; KYC-verified if
    `verified`."""

    def provision():
        seed_kyc_reference_data()
        clerk_id = f"{name}_{uuid.uuid4().hex[:8]}"
        user = UserController().ensure_provisioned(
            clerk_id, lambda: f"{clerk_id}@example.com", lambda: name.title()
        )
        user.last_name = last_name
        db.session.commit()
        if verified:
            insert_application(
                user.id, KycStatus.APPROVED, tier_granted=KYC_TIER_VERIFIED
            )
        return Person(user.id, user.base_reference)

    return _in_session(provision)


def _stokvel(organiser: Person, *, deactivated: bool = False) -> uuid.UUID:
    """A ZAR stokvel and its Organiser's membership, written directly."""

    def insert():
        stokvel = Stokvel(
            organiser_user_id=organiser.id,
            name="Family",
            currency=CURRENCY_ZAR,
            contribution_amount=Decimal("10"),
            deactivated_at=datetime.now(UTC) if deactivated else None,
        )
        db.session.add(stokvel)
        db.session.flush()
        _add_member(stokvel.id, organiser.id)
        db.session.commit()
        return stokvel.id

    return _in_session(insert)


def _add_member(stokvel_id, user_id, invitation_id=None) -> None:
    account = AccountRepository().get_user_account(user_id, CURRENCY_ZAR)
    db.session.add(
        StokvelMember(
            stokvel_id=stokvel_id,
            user_id=user_id,
            account_id=account.account_id,
            invitation_id=invitation_id,
        )
    )
    db.session.flush()


def _invitation_row(stokvel_id, invitee: Person, status, organiser_id):
    answered = status != StokvelInvitationStatus.PENDING
    invitation = StokvelInvitation(
        stokvel_id=stokvel_id,
        invitee_user_id=invitee.id,
        invited_by_user_id=organiser_id,
        status=status.value,
        status_changed_at=datetime.now(UTC) if answered else None,
        status_changed_by_user_id=(
            None
            if not answered
            else organiser_id
            if status == StokvelInvitationStatus.REVOKED
            else invitee.id
        ),
    )
    db.session.add(invitation)
    db.session.flush()
    return invitation


def _invitation(
    stokvel_id, invitee: Person, status=StokvelInvitationStatus.PENDING
) -> uuid.UUID:
    """An invitation written directly, from the stokvel's Organiser."""

    def insert():
        organiser_id = db.session.get(Stokvel, stokvel_id).organiser_user_id
        invitation = _invitation_row(stokvel_id, invitee, status, organiser_id)
        db.session.commit()
        return invitation.id

    return _in_session(insert)


def _member_of(stokvel_id, person: Person) -> None:
    """`person` joins by an accepted invitation, written directly."""

    def join():
        organiser_id = db.session.get(Stokvel, stokvel_id).organiser_user_id
        invitation = _invitation_row(
            stokvel_id, person, StokvelInvitationStatus.ACCEPTED, organiser_id
        )
        _add_member(stokvel_id, person.id, invitation.id)
        db.session.commit()

    _in_session(join)


def _members(stokvel_id) -> set[uuid.UUID]:
    return set(
        _in_session(
            lambda: db.session.scalars(
                select(StokvelMember.user_id).where(
                    StokvelMember.stokvel_id == stokvel_id,
                    StokvelMember.left_at.is_(None),
                )
            ).all()
        )
    )


def _open_cycle(stokvel_id, status: StokvelCycleStatus) -> None:
    """Cycle 1 of the stokvel in `status`, with no member rows, written
    directly."""

    def insert():
        started = status != StokvelCycleStatus.FORMING
        db.session.add(
            StokvelCycle(
                stokvel_id=stokvel_id,
                cycle_number=1,
                status=status.value,
                total_rounds=2 if started else None,
                current_round=0 if started else None,
                started_at=datetime.now(UTC) if started else None,
            )
        )
        db.session.commit()

    _in_session(insert)


def _cycle_members(stokvel_id) -> set[uuid.UUID]:
    """Users with a row in any cycle of the stokvel."""
    return set(
        _in_session(
            lambda: db.session.scalars(
                select(StokvelMember.user_id)
                .join(
                    StokvelCycleMember,
                    StokvelCycleMember.member_id == StokvelMember.id,
                )
                .where(StokvelMember.stokvel_id == stokvel_id)
            ).all()
        )
    )


def _invitations(stokvel_id) -> list[StokvelInvitation]:
    return _in_session(
        lambda: db.session.scalars(
            select(StokvelInvitation).where(StokvelInvitation.stokvel_id == stokvel_id)
        ).all()
    )


def _get_invitation(invitation_id) -> StokvelInvitation:
    return _in_session(lambda: db.session.get(StokvelInvitation, invitation_id))


class Api:
    """Calls the routes as a chosen user."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

        def caller(request: Request) -> User:
            return User(id=uuid.UUID(request.headers[USER_HEADER]))

        client.app.dependency_overrides[get_current_user] = caller

    def invite(self, as_: Person, stokvel_id, reference: str):
        return self.client.post(
            f"/stokvels/{stokvel_id}/invitations",
            json={"account_reference": reference},
            headers={USER_HEADER: str(as_.id)},
        )

    def accept(self, as_: Person, invitation_id):
        return self.client.post(
            f"/invitations/{invitation_id}/accept",
            headers={USER_HEADER: str(as_.id)},
        )

    def decline(self, as_: Person, invitation_id):
        return self.client.post(
            f"/invitations/{invitation_id}/decline",
            headers={USER_HEADER: str(as_.id)},
        )

    def revoke(self, as_: Person, invitation_id):
        return self.client.post(
            f"/invitations/{invitation_id}/revoke",
            headers={USER_HEADER: str(as_.id)},
        )

    def list(self, as_: Person):
        return self.client.get("/stokvels", headers={USER_HEADER: str(as_.id)})


@pytest.fixture
def api():
    with TestClient(create_app(TestConfig)) as client:
        yield Api(client)
        client.app.dependency_overrides.clear()


def _refused(response, status_code: int, code: str | None = None) -> None:
    assert response.status_code == status_code, response.text
    assert response.json().get("code") == code


# --- the examples from #209 --------------------------------------------------


def test_the_original_examples(api):
    """#209's examples, by reference: a ZAR account is invited, a USD one is
    refused, an unverified invitee is refused, and accepting makes a Member."""
    organiser = _person("sipho")
    thandi = _person("thandi", last_name="Mokoena")
    lerato = _person("lerato")
    _in_session(
        lambda: (
            AccountRepository().get_or_create_user_account(
                lerato.id, lerato.base_reference, CURRENCY_USD
            ),
            db.session.commit(),
        )
    )
    unverified = _person("unverified", verified=False)
    stokvel_id = _stokvel(organiser)

    invited = api.invite(organiser, stokvel_id, thandi.ref())
    assert invited.status_code == 201, invited.text
    body = invited.json()
    assert body["stokvel_id"] == str(stokvel_id)
    assert body["invitee_name"] == "Thandi M."
    assert body["account_reference"] == thandi.ref()
    assert body["status"] == "pending"

    _refused(
        api.invite(organiser, stokvel_id, lerato.ref(CURRENCY_USD)),
        422,
        "invitee_currency_mismatch",
    )
    _refused(
        api.invite(organiser, stokvel_id, unverified.ref()),
        403,
        "invitee_not_verified",
    )

    accepted = api.accept(thandi, body["invitation_id"])
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["stokvel_id"] == str(stokvel_id)
    assert accepted.json()["member_count"] == 2
    assert accepted.json()["is_organiser"] is False
    assert _members(stokvel_id) == {organiser.id, thandi.id}


# --- invite --------------------------------------------------------------------


def test_invite_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(
        f"/stokvels/{uuid.uuid4()}/invitations", json={"account_reference": "x-zar"}
    )

    assert response.status_code == 401


def test_invite_records_a_pending_invitation_and_no_member(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)

    response = api.invite(organiser, stokvel_id, f"  {invitee.ref()}  ")

    assert response.status_code == 201, response.text
    [invitation] = _invitations(stokvel_id)
    assert invitation.invitee_user_id == invitee.id
    assert invitation.invited_by_user_id == organiser.id
    assert invitation.status == "pending"
    assert _members(stokvel_id) == {organiser.id}


def test_invite_to_an_unknown_stokvel_is_not_found(api):
    _refused(api.invite(_person("sipho"), uuid.uuid4(), _person().ref()), 404)


def test_invite_to_someone_elses_stokvel_is_not_found(api):
    """The same 404 as for an unknown id, as row-level security answers."""
    stokvel_id = _stokvel(_person("sipho"))

    _refused(api.invite(_person("outsider"), stokvel_id, _person().ref()), 404)


def test_a_member_who_is_not_the_organiser_cannot_invite(api):
    stokvel_id = _stokvel(_person("sipho"))
    member = _person("member")
    _member_of(stokvel_id, member)

    _refused(api.invite(member, stokvel_id, _person().ref()), 403, "not_organiser")


def test_invite_with_an_unknown_reference_is_not_found(api):
    organiser = _person("sipho")

    _refused(api.invite(organiser, _stokvel(organiser), "nobody9-zar"), 404)


def test_the_organiser_cannot_invite_themselves(api):
    organiser = _person("sipho")

    _refused(api.invite(organiser, _stokvel(organiser), organiser.ref()), 400)


def test_a_token_account_is_the_wrong_currency(api):
    organiser, invitee = _person("sipho"), _person()

    _refused(
        api.invite(organiser, _stokvel(organiser), invitee.ref(CURRENCY_TOKEN)),
        422,
        "invitee_currency_mismatch",
    )


def test_a_current_member_cannot_be_invited(api):
    organiser, member = _person("sipho"), _person("member")
    stokvel_id = _stokvel(organiser)
    _member_of(stokvel_id, member)

    _refused(api.invite(organiser, stokvel_id, member.ref()), 409, "already_a_member")


def test_a_second_pending_invitation_is_refused(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    api.invite(organiser, stokvel_id, invitee.ref())

    _refused(
        api.invite(organiser, stokvel_id, invitee.ref()),
        409,
        "invitation_already_pending",
    )
    assert len(_invitations(stokvel_id)) == 1


def test_a_concurrent_duplicate_that_slips_past_is_still_refused(api, monkeypatch):
    """The one-pending index refuses an invite that passed the checks before
    a concurrent one committed: reported as already pending."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    _invitation(stokvel_id, invitee)
    members = invitations_route.controller._members
    monkeypatch.setattr(members, "get_active_member", lambda *_: None)

    _refused(
        api.invite(organiser, stokvel_id, invitee.ref()),
        409,
        "invitation_already_pending",
    )


def test_a_declined_invitee_can_be_invited_again(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    _invitation(stokvel_id, invitee, StokvelInvitationStatus.DECLINED)

    assert api.invite(organiser, stokvel_id, invitee.ref()).status_code == 201


def test_a_full_stokvel_takes_no_invitations(api):
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser)
    for i in range(MAX_MEMBERS - 1):
        _member_of(stokvel_id, _person(f"member{i}"))

    _refused(
        api.invite(organiser, stokvel_id, _person().ref()), 422, "too_many_members"
    )


def test_invitations_may_outnumber_the_free_places(api):
    """The cap holds at accepting, not inviting."""
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser)

    for i in range(MAX_MEMBERS):
        response = api.invite(organiser, stokvel_id, _person(f"invitee{i}").ref())
        assert response.status_code == 201, response.text


def test_a_deactivated_stokvel_takes_no_invitations(api):
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser, deactivated=True)

    _refused(
        api.invite(organiser, stokvel_id, _person().ref()), 409, "stokvel_deactivated"
    )


@pytest.mark.parametrize("reference", ["", "   ", "x" * 65])
def test_invite_rejects_an_invalid_reference(api, reference):
    organiser = _person("sipho")

    response = api.invite(organiser, _stokvel(organiser), reference)

    assert response.status_code == 422


# --- accept --------------------------------------------------------------------


def test_accepting_records_who_answered_and_when(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)

    assert api.accept(invitee, invitation_id).status_code == 200

    invitation = _get_invitation(invitation_id)
    assert invitation.status == "accepted"
    assert invitation.status_changed_by_user_id == invitee.id
    assert invitation.status_changed_at is not None
    member = _in_session(
        lambda: db.session.scalars(
            select(StokvelMember).where(StokvelMember.user_id == invitee.id)
        ).one()
    )
    assert member.invitation_id == invitation_id
    zar = _in_session(
        lambda: AccountRepository().get_user_account(invitee.id, CURRENCY_ZAR)
    )
    assert member.account_id == zar.account_id


def test_after_accepting_the_stokvel_lists_and_the_invitation_does_not(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)
    before = api.list(invitee).json()
    assert [i["invitation_id"] for i in before["invitations"]] == [str(invitation_id)]

    api.accept(invitee, invitation_id)

    after = api.list(invitee).json()
    assert [s["stokvel_id"] for s in after["stokvels"]] == [str(stokvel_id)]
    assert after["invitations"] == []


def test_a_fellow_member_cannot_answer_someone_elses_invitation(api):
    organiser, member, invitee = _person("sipho"), _person("member"), _person()
    stokvel_id = _stokvel(organiser)
    _member_of(stokvel_id, member)
    invitation_id = _invitation(stokvel_id, invitee)

    _refused(api.accept(member, invitation_id), 403, "not_invitee")
    _refused(api.accept(organiser, invitation_id), 403, "not_invitee")
    _refused(api.decline(member, invitation_id), 403, "not_invitee")
    assert _get_invitation(invitation_id).status == "pending"


def test_an_outsider_gets_not_found(api):
    stokvel_id = _stokvel(_person("sipho"))
    invitation_id = _invitation(stokvel_id, _person())

    _refused(api.accept(_person("outsider"), invitation_id), 404)
    _refused(api.decline(_person("outsider"), invitation_id), 404)


def test_an_unknown_invitation_is_not_found(api):
    _refused(api.accept(_person(), uuid.uuid4()), 404)
    _refused(api.decline(_person(), uuid.uuid4()), 404)


@pytest.mark.parametrize(
    "status",
    [
        StokvelInvitationStatus.ACCEPTED,
        StokvelInvitationStatus.DECLINED,
        StokvelInvitationStatus.REVOKED,
        StokvelInvitationStatus.LAPSED,
    ],
)
def test_an_answered_invitation_cannot_be_answered_again(api, status):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee, status)

    _refused(api.accept(invitee, invitation_id), 409, "invitation_not_pending")
    _refused(api.decline(invitee, invitation_id), 409, "invitation_not_pending")
    assert _members(stokvel_id) == {organiser.id}


def test_accepting_twice_is_refused(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)

    assert api.accept(invitee, invitation_id).status_code == 200
    _refused(api.accept(invitee, invitation_id), 409, "invitation_not_pending")
    assert _members(stokvel_id) == {organiser.id, invitee.id}


def test_a_concurrent_answer_that_slips_past_is_refused(api, monkeypatch):
    """The guarded update refuses an answer when the invitation stopped
    being pending after it was read."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)
    repo = invitations_route.controller._invitations
    monkeypatch.setattr(repo, "set_status_if_pending", lambda *_, **__: False)

    _refused(api.accept(invitee, invitation_id), 409, "invitation_not_pending")
    assert _members(stokvel_id) == {organiser.id}


def test_accepting_into_a_full_stokvel_is_refused(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)
    for i in range(MAX_MEMBERS - 1):
        _member_of(stokvel_id, _person(f"member{i}"))

    _refused(api.accept(invitee, invitation_id), 422, "too_many_members")
    assert _get_invitation(invitation_id).status == "pending"


def test_a_former_member_frees_their_place(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)
    others = [_person(f"member{i}") for i in range(MAX_MEMBERS - 1)]
    for other in others:
        _member_of(stokvel_id, other)

    def leave():
        row = db.session.scalars(
            select(StokvelMember).where(StokvelMember.user_id == others[0].id)
        ).one()
        row.left_at = datetime.now(UTC)
        db.session.commit()

    _in_session(leave)

    assert api.accept(invitee, invitation_id).status_code == 200


def test_accepting_needs_an_account_in_the_stokvel_currency(api):
    """Contributions are paid from it; it is never opened on their behalf."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    _in_session(
        lambda: (
            db.session.execute(
                Stokvel.__table__.update()
                .where(Stokvel.id == stokvel_id)
                .values(currency=CURRENCY_USD)
            ),
            db.session.commit(),
        )
    )
    invitation_id = _invitation(stokvel_id, invitee)

    response = api.accept(invitee, invitation_id)

    _refused(response, 400)
    assert "USD" in response.json()["detail"]
    assert _get_invitation(invitation_id).status == "pending"


def test_an_invitee_whose_verification_lapsed_cannot_accept(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)
    _in_session(
        lambda: insert_application(
            invitee.id,
            KycStatus.REJECTED,
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
    )

    response = api.accept(invitee, invitation_id)

    _refused(response, 403)
    assert "verified" in response.json()["detail"]
    assert _get_invitation(invitation_id).status == "pending"


def test_an_invitee_renewing_their_verification_is_invited_and_accepts(api):
    """An open renewal leaves the approval before it in force."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    _in_session(
        lambda: insert_application(
            invitee.id,
            KycStatus.SUBMITTED,
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
    )

    invited = api.invite(organiser, stokvel_id, invitee.ref())
    assert invited.status_code == 201, invited.text
    accepted = api.accept(invitee, invited.json()["invitation_id"])

    assert accepted.status_code == 200, accepted.text
    assert _members(stokvel_id) == {organiser.id, invitee.id}


def test_an_invitation_to_a_deactivated_stokvel_cannot_be_accepted(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser, deactivated=True)
    invitation_id = _invitation(stokvel_id, invitee)

    _refused(api.accept(invitee, invitation_id), 409, "stokvel_deactivated")


def test_an_invitation_to_a_deactivated_stokvel_is_not_listed(api):
    """Reviewer note on #339: it could not be accepted, so it is hidden."""
    organiser, invitee = _person("sipho"), _person()
    live = _stokvel(organiser)
    _invitation(live, invitee)
    _invitation(_stokvel(organiser, deactivated=True), invitee)

    listed = api.list(invitee).json()["invitations"]

    assert [i["stokvel_id"] for i in listed] == [str(live)]


def test_a_failed_member_insert_leaves_the_invitation_pending(api, monkeypatch):
    """Accepting is one transaction: the status change rolls back with it."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)

    def fail(_member):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(invitations_route.controller._members, "add", fail)

    with pytest.raises(RuntimeError, match="insert failed"):
        api.accept(invitee, invitation_id)

    assert _get_invitation(invitation_id).status == "pending"
    assert _members(stokvel_id) == {organiser.id}


def test_accepting_during_a_forming_cycle_adds_a_cycle_row(api):
    """The new member can then choose a beneficiary and be placed in the
    payout order (R2-09)."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    _open_cycle(stokvel_id, StokvelCycleStatus.FORMING)
    invitation_id = _invitation(stokvel_id, invitee)

    assert api.accept(invitee, invitation_id).status_code == 200

    assert _cycle_members(stokvel_id) == {invitee.id}


def test_accepting_during_an_active_cycle_adds_no_cycle_row(api):
    """They join the next cycle (#237), not the one already running."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    _open_cycle(stokvel_id, StokvelCycleStatus.ACTIVE)
    invitation_id = _invitation(stokvel_id, invitee)

    assert api.accept(invitee, invitation_id).status_code == 200

    assert _cycle_members(stokvel_id) == set()


def test_accepting_into_a_stokvel_with_no_cycle_adds_no_cycle_row(api):
    """A stokvel made before cycles opened at creation: the setup routes
    open its cycle on demand."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)

    assert api.accept(invitee, invitation_id).status_code == 200

    assert _members(stokvel_id) == {organiser.id, invitee.id}
    assert _cycle_members(stokvel_id) == set()


# --- decline -------------------------------------------------------------------


def test_declining_records_who_answered_and_adds_no_member(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)

    response = api.decline(invitee, invitation_id)

    assert response.status_code == 204
    invitation = _get_invitation(invitation_id)
    assert invitation.status == "declined"
    assert invitation.status_changed_by_user_id == invitee.id
    assert _members(stokvel_id) == {organiser.id}
    assert api.list(invitee).json()["invitations"] == []


def test_answering_anonymously_is_rejected(anonymous_client):
    for action in ("accept", "decline", "revoke"):
        response = anonymous_client.post(f"/invitations/{uuid.uuid4()}/{action}")
        assert response.status_code == 401


# --- revoke --------------------------------------------------------------------


def test_revoking_records_who_and_when_and_the_invitee_cannot_accept(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)

    response = api.revoke(organiser, invitation_id)

    assert response.status_code == 204, response.text
    invitation = _get_invitation(invitation_id)
    assert invitation.status == "revoked"
    assert invitation.status_changed_by_user_id == organiser.id
    assert invitation.status_changed_at is not None
    _refused(api.accept(invitee, invitation_id), 409, "invitation_not_pending")
    assert api.list(invitee).json()["invitations"] == []
    assert _members(stokvel_id) == {organiser.id}


def test_a_revoked_invitee_can_be_invited_again(api):
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)
    api.revoke(organiser, invitation_id)

    assert api.invite(organiser, stokvel_id, invitee.ref()).status_code == 201
    assert sorted(i.status for i in _invitations(stokvel_id)) == [
        "pending",
        "revoked",
    ]


def test_revoking_twice_is_refused(api):
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, _person())

    assert api.revoke(organiser, invitation_id).status_code == 204
    _refused(api.revoke(organiser, invitation_id), 409, "invitation_not_pending")


@pytest.mark.parametrize(
    "status",
    [
        StokvelInvitationStatus.ACCEPTED,
        StokvelInvitationStatus.DECLINED,
        StokvelInvitationStatus.LAPSED,
    ],
)
def test_an_answered_invitation_cannot_be_revoked(api, status):
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, _person(), status)

    _refused(api.revoke(organiser, invitation_id), 409, "invitation_not_pending")
    assert _get_invitation(invitation_id).status == status.value


def test_only_the_organiser_revokes(api):
    """The invitee and fellow members can see the invitation, so get 403;
    anyone else gets 404."""
    organiser, member, invitee = _person("sipho"), _person("member"), _person()
    stokvel_id = _stokvel(organiser)
    _member_of(stokvel_id, member)
    invitation_id = _invitation(stokvel_id, invitee)

    _refused(api.revoke(member, invitation_id), 403, "not_organiser")
    _refused(api.revoke(invitee, invitation_id), 403, "not_organiser")
    _refused(api.revoke(_person("outsider"), invitation_id), 404)
    assert _get_invitation(invitation_id).status == "pending"


def test_revoking_an_unknown_invitation_is_not_found(api):
    _refused(api.revoke(_person(), uuid.uuid4()), 404)


def test_an_invitation_to_a_deactivated_stokvel_can_be_revoked(api):
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser, deactivated=True)
    invitation_id = _invitation(stokvel_id, _person())

    assert api.revoke(organiser, invitation_id).status_code == 204


def test_a_concurrent_answer_beats_the_revoke(api, monkeypatch):
    """The guarded update refuses a revoke when the invitee answered after
    the invitation was read."""
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, _person())
    repo = invitations_route.controller._invitations
    monkeypatch.setattr(repo, "set_status_if_pending", lambda *_, **__: False)

    _refused(api.revoke(organiser, invitation_id), 409, "invitation_not_pending")


# --- under Postgres row-level security --------------------------------------


@pytest.fixture
def pg_api(postgres_app):
    with TestClient(postgres_app) as client:
        yield Api(client)
        postgres_app.dependency_overrides.clear()


@pytest.mark.postgres
def test_under_row_security_the_organiser_invites_a_verified_user(pg_api):
    """The Organiser cannot read the invitee's KYC applications; the lookup
    still finds them verified, and an unverified invitee is still refused."""
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser)

    invited = pg_api.invite(organiser, stokvel_id, _person().ref())
    refused = pg_api.invite(
        organiser, stokvel_id, _person("unverified", verified=False).ref()
    )

    assert invited.status_code == 201, invited.text
    _refused(refused, 403, "invitee_not_verified")


@pytest.mark.postgres
def test_under_row_security_an_invitee_accepts_and_declines(pg_api):
    organiser, joiner, decliner = _person("sipho"), _person(), _person("decliner")
    stokvel_id = _stokvel(organiser)
    to_join = _invitation(stokvel_id, joiner)
    to_decline = _invitation(stokvel_id, decliner)

    accepted = pg_api.accept(joiner, to_join)
    declined = pg_api.decline(decliner, to_decline)

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["member_count"] == 2
    assert declined.status_code == 204, declined.text
    assert _members(stokvel_id) == {organiser.id, joiner.id}


@pytest.mark.postgres
def test_under_row_security_an_invitee_joins_the_forming_cycle(pg_api):
    """The invitee can see the cycle only once they are a member, and may
    insert their own cycle row."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    _open_cycle(stokvel_id, StokvelCycleStatus.FORMING)
    invitation_id = _invitation(stokvel_id, invitee)

    accepted = pg_api.accept(invitee, invitation_id)

    assert accepted.status_code == 200, accepted.text
    assert _cycle_members(stokvel_id) == {invitee.id}


@pytest.mark.postgres
def test_under_row_security_the_cap_holds_for_an_invitee(pg_api):
    """The invitee cannot read the member rows; the count still sees them."""
    organiser, invitee = _person("sipho"), _person()
    stokvel_id = _stokvel(organiser)
    invitation_id = _invitation(stokvel_id, invitee)
    for i in range(MAX_MEMBERS - 1):
        _member_of(stokvel_id, _person(f"member{i}"))

    _refused(pg_api.accept(invitee, invitation_id), 422, "too_many_members")


@pytest.mark.postgres
def test_under_row_security_two_accepts_for_the_last_place_admit_one(
    pg_api, monkeypatch
):
    """The stokvel row lock makes the second accept wait, then count the
    first one's member and be refused.

    Each accept waits briefly at a barrier after counting. Without the lock
    both would count before either inserts, meet there and both join; with
    it, the second cannot count until the first commits, so the first's wait
    times out alone."""
    organiser = _person("sipho")
    stokvel_id = _stokvel(organiser)
    for i in range(MAX_MEMBERS - 2):
        _member_of(stokvel_id, _person(f"member{i}"))
    invitees = [_person("first"), _person("second")]
    invitations = [_invitation(stokvel_id, person) for person in invitees]

    members = invitations_route.controller._members
    count_active = members.count_active
    both_counted = threading.Barrier(2, timeout=1)

    def count_then_wait(stokvel_id):
        count = count_active(stokvel_id)
        try:
            both_counted.wait()
        except threading.BrokenBarrierError:
            pass
        return count

    monkeypatch.setattr(members, "count_active", count_then_wait)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda pair: pg_api.accept(*pair),
                zip(invitees, invitations, strict=True),
            )
        )

    assert sorted(r.status_code for r in responses) == [200, 422]
    assert len(_members(stokvel_id)) == MAX_MEMBERS


@pytest.mark.postgres
def test_under_row_security_the_organiser_revokes(pg_api):
    """The Organiser's revoke passes `stokvel_invitations_update`; a member,
    who can see the invitation, is refused; an outsider cannot see it."""
    organiser, member, invitee = _person("sipho"), _person("member"), _person()
    stokvel_id = _stokvel(organiser)
    _member_of(stokvel_id, member)
    invitation_id = _invitation(stokvel_id, invitee)

    _refused(pg_api.revoke(member, invitation_id), 403, "not_organiser")
    _refused(pg_api.revoke(_person("outsider"), invitation_id), 404)
    revoked = pg_api.revoke(organiser, invitation_id)
    invited_again = pg_api.invite(organiser, stokvel_id, invitee.ref())

    assert revoked.status_code == 204, revoked.text
    invitation = _get_invitation(invitation_id)
    assert invitation.status == "revoked"
    assert invitation.status_changed_by_user_id == organiser.id
    assert invited_again.status_code == 201, invited_again.text


@pytest.mark.postgres
def test_under_row_security_an_outsider_cannot_see_an_invitation(pg_api):
    stokvel_id = _stokvel(_person("sipho"))
    invitation_id = _invitation(stokvel_id, _person())

    _refused(pg_api.accept(_person("outsider"), invitation_id), 404)
