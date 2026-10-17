"""`PUT /stokvels/{id}/payout-order` (R2-09).

On SQLite, which has no row-level security, except the tests marked
`postgres`, which run the same routes under it (TEST_DATABASE_URL). The
database's own write rules for the cycle tables are in
`test_stokvel_cycle_models.py`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
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
from sqlalchemy import select
from tests.kyc_helpers import insert_application, seed_kyc_reference_data

# Picks the caller per request, as in test_stokvel_invitations_route.py.
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


def _person(name: str = "thandi", last_name: str | None = None) -> Person:
    """A KYC-verified user with their sign-up ZAR and token accounts."""

    def provision():
        seed_kyc_reference_data()
        clerk_id = f"{name}_{uuid.uuid4().hex[:8]}"
        user = UserController().ensure_provisioned(
            clerk_id, lambda: f"{clerk_id}@example.com", lambda: name.title()
        )
        user.last_name = last_name
        db.session.commit()
        insert_application(user.id, KycStatus.APPROVED, tier_granted=KYC_TIER_VERIFIED)
        return Person(user.id)

    return _in_session(provision)


@dataclass(frozen=True)
class Group:
    """A stokvel and its members' `stokvel_members` ids, by person."""

    stokvel_id: uuid.UUID
    organiser: Person
    member_ids: dict[Person, uuid.UUID]

    def member_id(self, person: Person) -> uuid.UUID:
        return self.member_ids[person]


def _stokvel(
    organiser: Person,
    *others: Person,
    cycle: StokvelCycleStatus | None = StokvelCycleStatus.FORMING,
    deactivated: bool = False,
) -> Group:
    """A ZAR stokvel with `organiser` and `others` as current members,
    written directly. `cycle` is the status of its cycle 1, each member with
    an empty row while it is forming; None writes no cycle, as for a
    stokvel made before cycles opened at creation."""

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
        member_ids = {organiser: _add_member(stokvel, organiser)}
        for other in others:
            member_ids[other] = _add_member(stokvel, other, invited=True)
        if cycle is not None:
            row = _cycle(stokvel.id, cycle)
            stokvel.current_cycle_id = row.id
            if cycle == StokvelCycleStatus.FORMING:
                for member_id in member_ids.values():
                    db.session.add(
                        StokvelCycleMember(cycle_id=row.id, member_id=member_id)
                    )
        db.session.commit()
        return Group(stokvel.id, organiser, member_ids)

    return _in_session(insert)


def _add_member(stokvel: Stokvel, person: Person, *, invited=False) -> uuid.UUID:
    invitation_id = None
    if invited:
        invitation = StokvelInvitation(
            stokvel_id=stokvel.id,
            invitee_user_id=person.id,
            invited_by_user_id=stokvel.organiser_user_id,
            status=StokvelInvitationStatus.ACCEPTED.value,
            status_changed_at=datetime.now(UTC),
            status_changed_by_user_id=person.id,
        )
        db.session.add(invitation)
        db.session.flush()
        invitation_id = invitation.id
    account = AccountRepository().get_user_account(person.id, CURRENCY_ZAR)
    member = StokvelMember(
        stokvel_id=stokvel.id,
        user_id=person.id,
        account_id=account.account_id,
        invitation_id=invitation_id,
    )
    db.session.add(member)
    db.session.flush()
    return member.id


def _cycle(stokvel_id, status: StokvelCycleStatus, number: int = 1) -> StokvelCycle:
    started = status != StokvelCycleStatus.FORMING
    closed = status == StokvelCycleStatus.CLOSED
    now = datetime.now(UTC)
    cycle = StokvelCycle(
        stokvel_id=stokvel_id,
        cycle_number=number,
        status=status.value,
        total_rounds=2 if started else None,
        current_round=0 if started else None,
        started_at=now if started else None,
        closed_at=now if closed else None,
    )
    db.session.add(cycle)
    db.session.flush()
    return cycle


def _leave(member_id: uuid.UUID) -> None:
    def leave():
        db.session.get(StokvelMember, member_id).left_at = datetime.now(UTC)
        db.session.commit()

    _in_session(leave)


def _positions(stokvel_id) -> dict[uuid.UUID, int | None]:
    """Each cycle row's payout position, by member id, for the open cycle."""
    return dict(
        _in_session(
            lambda: db.session.execute(
                select(StokvelCycleMember.member_id, StokvelCycleMember.payout_position)
                .join(StokvelCycle, StokvelCycle.id == StokvelCycleMember.cycle_id)
                .where(
                    StokvelCycle.stokvel_id == stokvel_id,
                    StokvelCycle.status != StokvelCycleStatus.CLOSED.value,
                )
            ).all()
        )
    )


class Api:
    """Calls the routes as a chosen user."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

        def caller(request: Request) -> User:
            return User(id=uuid.UUID(request.headers[USER_HEADER]))

        client.app.dependency_overrides[get_current_user] = caller

    def payout_order(self, as_: Person, stokvel_id, member_ids):
        return self.client.put(
            f"/stokvels/{stokvel_id}/payout-order",
            json={"member_ids": [str(member_id) for member_id in member_ids]},
            headers={USER_HEADER: str(as_.id)},
        )


@pytest.fixture
def api():
    with TestClient(create_app(TestConfig)) as client:
        yield Api(client)
        client.app.dependency_overrides.clear()


def _refused(response, status_code: int, code: str | None = None) -> None:
    assert response.status_code == status_code, response.text
    assert response.json().get("code") == code


# --- payout order --------------------------------------------------------------


def test_the_organiser_sets_the_payout_order(api):
    organiser, thandi = _person("sipho", "Dlamini"), _person("thandi", "Mokoena")
    group = _stokvel(organiser, thandi)
    order = [group.member_id(thandi), group.member_id(organiser)]

    response = api.payout_order(organiser, group.stokvel_id, order)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "stokvel_id": str(group.stokvel_id),
        "cycle_number": 1,
        "order": [
            {
                "member_id": str(order[0]),
                "payout_position": 0,
                "name": "Thandi M.",
            },
            {
                "member_id": str(order[1]),
                "payout_position": 1,
                "name": "Sipho D.",
            },
        ],
    }
    assert _positions(group.stokvel_id) == {order[0]: 0, order[1]: 1}


def test_the_payout_order_can_be_set_again(api):
    """Positions are unique per cycle: swapping two must not trip that."""
    organiser, thandi, lerato = _person("sipho"), _person(), _person("lerato")
    group = _stokvel(organiser, thandi, lerato)
    first = [group.member_id(p) for p in (organiser, thandi, lerato)]
    swapped = [first[1], first[0], first[2]]

    assert api.payout_order(organiser, group.stokvel_id, first).status_code == 200
    response = api.payout_order(organiser, group.stokvel_id, swapped)

    assert response.status_code == 200, response.text
    assert _positions(group.stokvel_id) == {
        member_id: position for position, member_id in enumerate(swapped)
    }


def test_a_member_who_is_not_the_organiser_cannot_set_the_order(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    order = [group.member_id(organiser), group.member_id(thandi)]

    response = api.payout_order(thandi, group.stokvel_id, order)

    _refused(response, 403, "not_organiser")
    assert response.json()["detail"] == (
        "Only the stokvel's organiser can set the payout order."
    )
    assert set(_positions(group.stokvel_id).values()) == {None}


def test_an_outsider_gets_not_found(api):
    organiser = _person("sipho")
    group = _stokvel(organiser)

    _refused(
        api.payout_order(
            _person("outsider"), group.stokvel_id, [group.member_id(organiser)]
        ),
        404,
    )


def test_an_unknown_stokvel_is_not_found(api):
    _refused(api.payout_order(_person(), uuid.uuid4(), [uuid.uuid4()]), 404)


def test_a_former_member_gets_not_found(api):
    """They can still read the stokvel under row-level security, but are no
    longer a member of it."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    _leave(group.member_id(thandi))

    _refused(
        api.payout_order(thandi, group.stokvel_id, [group.member_id(organiser)]), 404
    )


@pytest.mark.parametrize(
    ("make_order", "detail"),
    [
        (
            lambda ids, _former: [ids[0], ids[1], ids[0]],
            "Each member can appear only once in the payout order.",
        ),
        (
            lambda ids, _former: [ids[0]],
            "The payout order must include every current member.",
        ),
        (
            lambda ids, _former: [ids[0], ids[1], uuid.uuid4()],
            "The payout order includes someone who isn't a member of this stokvel.",
        ),
        (
            lambda ids, former: [ids[0], ids[1], former],
            "The payout order includes a member who has left the stokvel.",
        ),
    ],
    ids=["duplicate", "missing", "unknown", "former"],
)
def test_the_order_must_be_every_current_member_once(api, make_order, detail):
    organiser, thandi, leaver = _person("sipho"), _person(), _person("leaver")
    group = _stokvel(organiser, thandi, leaver)
    _leave(group.member_id(leaver))
    current = [group.member_id(organiser), group.member_id(thandi)]

    response = api.payout_order(
        organiser, group.stokvel_id, make_order(current, group.member_id(leaver))
    )

    _refused(response, 422, "invalid_payout_order")
    assert response.json()["detail"] == detail
    assert set(_positions(group.stokvel_id).values()) == {None}


def test_a_member_of_another_stokvel_is_not_a_member_of_this_one(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser)
    elsewhere = _stokvel(thandi)

    response = api.payout_order(
        organiser,
        group.stokvel_id,
        [group.member_id(organiser), elsewhere.member_id(thandi)],
    )

    _refused(response, 422, "invalid_payout_order")
    assert "isn't a member" in response.json()["detail"]


def test_an_empty_order_is_refused(api):
    organiser = _person("sipho")
    group = _stokvel(organiser)

    _refused(api.payout_order(organiser, group.stokvel_id, []), 422)


def test_a_member_who_left_loses_their_place(api):
    """Their row stays (no deletes), with no position, so it neither blocks
    the new order nor counts as placed when the cycle starts."""
    organiser, thandi, leaver = _person("sipho"), _person(), _person("leaver")
    group = _stokvel(organiser, thandi, leaver)
    everyone = [group.member_id(p) for p in (leaver, organiser, thandi)]
    assert api.payout_order(organiser, group.stokvel_id, everyone).status_code == 200
    _leave(group.member_id(leaver))
    remaining = [group.member_id(thandi), group.member_id(organiser)]

    response = api.payout_order(organiser, group.stokvel_id, remaining)

    assert response.status_code == 200, response.text
    assert _positions(group.stokvel_id) == {
        group.member_id(thandi): 0,
        group.member_id(organiser): 1,
        group.member_id(leaver): None,
    }


def test_the_order_is_locked_once_the_cycle_has_started(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, cycle=StokvelCycleStatus.ACTIVE)
    order = [group.member_id(organiser), group.member_id(thandi)]

    response = api.payout_order(organiser, group.stokvel_id, order)

    _refused(response, 409, "cycle_locked")
    assert response.json()["detail"] == (
        "The payout order and beneficiaries are locked while a cycle is running."
    )


def test_after_the_last_cycle_closes_there_is_nothing_to_order(api):
    """The next cycle is opened by #237, not on demand."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, cycle=StokvelCycleStatus.CLOSED)
    order = [group.member_id(organiser), group.member_id(thandi)]

    _refused(
        api.payout_order(organiser, group.stokvel_id, order), 409, "cycle_not_forming"
    )


def test_a_deactivated_stokvel_takes_no_order(api):
    organiser = _person("sipho")
    group = _stokvel(organiser, deactivated=True)

    _refused(
        api.payout_order(organiser, group.stokvel_id, [group.member_id(organiser)]),
        409,
        "stokvel_deactivated",
    )


def test_a_stokvel_with_no_cycle_gets_its_first_one(api):
    """Made before cycles opened at creation: the Organiser's first order
    opens cycle 1, with a row for every current member."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, cycle=None)
    order = [group.member_id(thandi), group.member_id(organiser)]

    response = api.payout_order(organiser, group.stokvel_id, order)

    assert response.status_code == 200, response.text
    assert response.json()["cycle_number"] == 1
    assert _positions(group.stokvel_id) == {order[0]: 0, order[1]: 1}
    stokvel, cycle = _in_session(
        lambda: (
            db.session.get(Stokvel, group.stokvel_id),
            db.session.scalars(
                select(StokvelCycle).where(StokvelCycle.stokvel_id == group.stokvel_id)
            ).one(),
        )
    )
    assert cycle.status == "forming"
    assert stokvel.current_cycle_id == cycle.id


def test_a_member_with_no_cycle_row_gets_one(api):
    """A member who joined before members got a row on accepting."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)

    def drop_row():
        db.session.execute(
            StokvelCycleMember.__table__.delete().where(
                StokvelCycleMember.member_id == group.member_id(thandi)
            )
        )
        db.session.commit()

    _in_session(drop_row)
    order = [group.member_id(thandi), group.member_id(organiser)]

    assert api.payout_order(organiser, group.stokvel_id, order).status_code == 200
    assert _positions(group.stokvel_id) == {order[0]: 0, order[1]: 1}


def test_setting_the_order_anonymously_is_rejected(anonymous_client):
    response = anonymous_client.put(
        f"/stokvels/{uuid.uuid4()}/payout-order", json={"member_ids": []}
    )
    assert response.status_code == 401


# --- under Postgres row-level security --------------------------------------


@pytest.fixture
def pg_api(postgres_app):
    with TestClient(postgres_app) as client:
        yield Api(client)
        postgres_app.dependency_overrides.clear()


@pytest.mark.postgres
def test_under_row_security_the_organiser_sets_and_resets_the_order(pg_api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    first = [group.member_id(organiser), group.member_id(thandi)]

    assert pg_api.payout_order(organiser, group.stokvel_id, first).status_code == 200
    response = pg_api.payout_order(organiser, group.stokvel_id, first[::-1])

    assert response.status_code == 200, response.text
    assert _positions(group.stokvel_id) == {first[1]: 0, first[0]: 1}


@pytest.mark.postgres
def test_under_row_security_the_organiser_opens_a_missing_first_cycle(pg_api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, cycle=None)
    order = [group.member_id(thandi), group.member_id(organiser)]

    response = pg_api.payout_order(organiser, group.stokvel_id, order)

    assert response.status_code == 200, response.text
    assert _positions(group.stokvel_id) == {order[0]: 0, order[1]: 1}


@pytest.mark.postgres
def test_under_row_security_an_outsider_cannot_see_the_stokvel(pg_api):
    organiser = _person("sipho")
    group = _stokvel(organiser)

    _refused(
        pg_api.payout_order(
            _person("outsider"), group.stokvel_id, [group.member_id(organiser)]
        ),
        404,
    )
