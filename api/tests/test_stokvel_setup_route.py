"""`PUT /stokvels/{id}/payout-order` and
`PUT /stokvels/{id}/members/me/beneficiary` (R2-09).

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
from remitx_api.models.orm.account import CURRENCY_USD, CURRENCY_ZAR
from remitx_api.models.orm.beneficiary import Beneficiary, BeneficiaryRelationship
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
    rowless: tuple[Person, ...] = (),
) -> Group:
    """A ZAR stokvel with `organiser` and `others` as current members,
    written directly. `cycle` is the status of its cycle 1, each member with
    an empty row while it is forming, except those in `rowless` (members
    who joined before rows were added on accepting); None writes no cycle,
    as for a stokvel made before cycles opened at creation."""

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
                for person, member_id in member_ids.items():
                    if person in rowless:
                        continue
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


def _beneficiary(sender: Person, linked: Person, currency=CURRENCY_ZAR) -> uuid.UUID:
    """`sender`'s beneficiary `linked`, paid in `currency`, written directly
    (so without the check that `linked` holds an account in it)."""

    def insert():
        beneficiary = Beneficiary(
            sender_user_id=sender.id,
            linked_user_id=linked.id,
            payout_currency=currency,
            relationship=BeneficiaryRelationship.PARENT.value,
        )
        db.session.add(beneficiary)
        db.session.commit()
        return beneficiary.beneficiary_id

    return _in_session(insert)


def _open_usd_account(person: Person) -> None:
    def open_account():
        user = db.session.get(User, person.id)
        AccountRepository().open_user_account(
            user.id, user.base_reference, CURRENCY_USD
        )
        db.session.commit()

    _in_session(open_account)


def _start(stokvel_id) -> None:
    """Start the open cycle and lock its rows, as R2-10 will. Every row
    must already have its position and beneficiary."""

    def start():
        cycle = db.session.scalars(
            select(StokvelCycle).where(
                StokvelCycle.stokvel_id == stokvel_id,
                StokvelCycle.status == StokvelCycleStatus.FORMING.value,
            )
        ).one()
        rows = db.session.scalars(
            select(StokvelCycleMember).where(StokvelCycleMember.cycle_id == cycle.id)
        ).all()
        cycle.status = StokvelCycleStatus.ACTIVE.value
        cycle.total_rounds = len(rows)
        cycle.current_round = 0
        cycle.started_at = datetime.now(UTC)
        for row in rows:
            row.locked = True
        db.session.commit()

    _in_session(start)


def _beneficiary_exists(beneficiary_id: uuid.UUID) -> bool:
    return _in_session(lambda: db.session.get(Beneficiary, beneficiary_id)) is not None


def _choices(stokvel_id) -> dict[uuid.UUID, tuple[uuid.UUID | None, str | None]]:
    """Each open-cycle row's (beneficiary, payout currency), by member id."""
    return {
        member_id: (beneficiary_id, currency)
        for member_id, beneficiary_id, currency in _in_session(
            lambda: db.session.execute(
                select(
                    StokvelCycleMember.member_id,
                    StokvelCycleMember.payout_beneficiary_id,
                    StokvelCycleMember.payout_currency,
                )
                .join(StokvelCycle, StokvelCycle.id == StokvelCycleMember.cycle_id)
                .where(
                    StokvelCycle.stokvel_id == stokvel_id,
                    StokvelCycle.status != StokvelCycleStatus.CLOSED.value,
                )
            ).all()
        )
    }


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

    def beneficiary(self, as_: Person, stokvel_id, beneficiary_id):
        return self.client.put(
            f"/stokvels/{stokvel_id}/members/me/beneficiary",
            json={"beneficiary_id": str(beneficiary_id)},
            headers={USER_HEADER: str(as_.id)},
        )

    def delete_beneficiary(self, as_: Person, beneficiary_id):
        return self.client.delete(
            f"/beneficiaries/{beneficiary_id}", headers={USER_HEADER: str(as_.id)}
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
    group = _stokvel(organiser, thandi, rowless=(thandi,))
    order = [group.member_id(thandi), group.member_id(organiser)]

    assert api.payout_order(organiser, group.stokvel_id, order).status_code == 200
    assert _positions(group.stokvel_id) == {order[0]: 0, order[1]: 1}


def test_setting_the_order_anonymously_is_rejected(anonymous_client):
    response = anonymous_client.put(
        f"/stokvels/{uuid.uuid4()}/payout-order", json={"member_ids": []}
    )
    assert response.status_code == 401


# --- beneficiary ---------------------------------------------------------------


def test_a_member_chooses_their_beneficiary(api):
    """The payout currency is the beneficiary's own, copied onto the row."""
    organiser, thandi, mother = _person("sipho"), _person(), _person("mother")
    _open_usd_account(mother)
    group = _stokvel(organiser, thandi)
    beneficiary_id = _beneficiary(thandi, mother, CURRENCY_USD)

    response = api.beneficiary(thandi, group.stokvel_id, beneficiary_id)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "stokvel_id": str(group.stokvel_id),
        "cycle_number": 1,
        "member_id": str(group.member_id(thandi)),
        "beneficiary_id": str(beneficiary_id),
        "payout_currency": "USD",
    }
    assert _choices(group.stokvel_id) == {
        group.member_id(organiser): (None, None),
        group.member_id(thandi): (beneficiary_id, CURRENCY_USD),
    }


def test_the_beneficiary_can_be_changed(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    first = _beneficiary(thandi, _person("mother"))
    second = _beneficiary(thandi, _person("brother"))

    assert api.beneficiary(thandi, group.stokvel_id, first).status_code == 200
    response = api.beneficiary(thandi, group.stokvel_id, second)

    assert response.status_code == 200, response.text
    assert _choices(group.stokvel_id)[group.member_id(thandi)] == (
        second,
        CURRENCY_ZAR,
    )


def test_the_organiser_chooses_their_own_beneficiary_too(api):
    organiser = _person("sipho")
    group = _stokvel(organiser)
    beneficiary_id = _beneficiary(organiser, _person("mother"))

    response = api.beneficiary(organiser, group.stokvel_id, beneficiary_id)

    assert response.status_code == 200, response.text
    assert _choices(group.stokvel_id) == {
        group.member_id(organiser): (beneficiary_id, CURRENCY_ZAR)
    }


def test_someone_elses_beneficiary_is_not_found(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    theirs = _beneficiary(organiser, _person("mother"))

    response = api.beneficiary(thandi, group.stokvel_id, theirs)

    _refused(response, 404)
    assert response.json()["detail"] == "Beneficiary not found"
    assert _choices(group.stokvel_id)[group.member_id(thandi)] == (None, None)


def test_an_unknown_beneficiary_is_not_found(api):
    organiser = _person("sipho")
    group = _stokvel(organiser)

    _refused(api.beneficiary(organiser, group.stokvel_id, uuid.uuid4()), 404)


def test_the_recipient_must_still_hold_the_payout_account(api):
    """Re-checked at choosing: a beneficiary in USD whose person holds only
    ZAR is refused, as when adding the beneficiary."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    beneficiary_id = _beneficiary(thandi, _person("mother"), CURRENCY_USD)

    response = api.beneficiary(thandi, group.stokvel_id, beneficiary_id)

    _refused(response, 400)
    assert response.json()["detail"] == (
        "They don't have a USD account. They can be paid in ZAR."
    )
    assert _choices(group.stokvel_id)[group.member_id(thandi)] == (None, None)


def test_an_outsider_cannot_choose_a_beneficiary(api):
    outsider = _person("outsider")
    group = _stokvel(_person("sipho"))
    beneficiary_id = _beneficiary(outsider, _person("mother"))

    _refused(api.beneficiary(outsider, group.stokvel_id, beneficiary_id), 404)


def test_the_beneficiary_is_locked_once_the_cycle_has_started(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, cycle=StokvelCycleStatus.ACTIVE)
    beneficiary_id = _beneficiary(thandi, _person("mother"))

    _refused(
        api.beneficiary(thandi, group.stokvel_id, beneficiary_id), 409, "cycle_locked"
    )


def test_after_the_last_cycle_closes_there_is_no_beneficiary_to_choose(api):
    organiser = _person("sipho")
    group = _stokvel(organiser, cycle=StokvelCycleStatus.CLOSED)
    beneficiary_id = _beneficiary(organiser, _person("mother"))

    _refused(
        api.beneficiary(organiser, group.stokvel_id, beneficiary_id),
        409,
        "cycle_not_forming",
    )


def test_a_deactivated_stokvel_takes_no_beneficiary(api):
    organiser = _person("sipho")
    group = _stokvel(organiser, deactivated=True)
    beneficiary_id = _beneficiary(organiser, _person("mother"))

    _refused(
        api.beneficiary(organiser, group.stokvel_id, beneficiary_id),
        409,
        "stokvel_deactivated",
    )


def test_a_member_waits_for_the_organiser_to_open_a_missing_cycle(api):
    """Row-level security lets only the Organiser insert a cycle, so a
    member of a stokvel with none is refused until the Organiser opens it."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, cycle=None)
    beneficiary_id = _beneficiary(thandi, _person("mother"))

    _refused(
        api.beneficiary(thandi, group.stokvel_id, beneficiary_id),
        409,
        "cycle_not_forming",
    )
    assert _choices(group.stokvel_id) == {}


def test_the_organiser_opens_a_missing_cycle_by_choosing(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, cycle=None)
    beneficiary_id = _beneficiary(organiser, _person("mother"))

    response = api.beneficiary(organiser, group.stokvel_id, beneficiary_id)

    assert response.status_code == 200, response.text
    assert _choices(group.stokvel_id) == {
        group.member_id(organiser): (beneficiary_id, CURRENCY_ZAR),
        group.member_id(thandi): (None, None),
    }


def test_a_member_with_no_cycle_row_gets_one_by_choosing(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, rowless=(thandi,))
    beneficiary_id = _beneficiary(thandi, _person("mother"))

    assert api.beneficiary(thandi, group.stokvel_id, beneficiary_id).status_code == 200
    assert _choices(group.stokvel_id)[group.member_id(thandi)] == (
        beneficiary_id,
        CURRENCY_ZAR,
    )


def test_choosing_anonymously_is_rejected(anonymous_client):
    response = anonymous_client.put(
        f"/stokvels/{uuid.uuid4()}/members/me/beneficiary",
        json={"beneficiary_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401


# --- removing a beneficiary a stokvel pays -------------------------------------


def test_a_beneficiary_chosen_for_a_forming_cycle_cannot_be_removed(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    beneficiary_id = _beneficiary(thandi, _person("mother"))
    assert api.beneficiary(thandi, group.stokvel_id, beneficiary_id).status_code == 200

    _refused(
        api.delete_beneficiary(thandi, beneficiary_id),
        409,
        "beneficiary_in_use_by_stokvel",
    )
    assert _beneficiary_exists(beneficiary_id)
    assert _choices(group.stokvel_id)[group.member_id(thandi)] == (
        beneficiary_id,
        CURRENCY_ZAR,
    )


def test_a_beneficiary_a_locked_cycle_pays_cannot_be_removed(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    order = [group.member_id(organiser), group.member_id(thandi)]
    assert api.payout_order(organiser, group.stokvel_id, order).status_code == 200
    chosen = {
        organiser: _beneficiary(organiser, _person("brother")),
        thandi: _beneficiary(thandi, _person("mother")),
    }
    for person, beneficiary_id in chosen.items():
        assert (
            api.beneficiary(person, group.stokvel_id, beneficiary_id).status_code == 200
        )
    _start(group.stokvel_id)

    _refused(
        api.delete_beneficiary(thandi, chosen[thandi]),
        409,
        "beneficiary_in_use_by_stokvel",
    )
    assert _beneficiary_exists(chosen[thandi])


def test_a_beneficiary_no_longer_chosen_can_be_removed(api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    first = _beneficiary(thandi, _person("mother"))
    second = _beneficiary(thandi, _person("brother"))
    assert api.beneficiary(thandi, group.stokvel_id, first).status_code == 200
    assert api.beneficiary(thandi, group.stokvel_id, second).status_code == 200

    response = api.delete_beneficiary(thandi, first)

    assert response.status_code == 204, response.text
    assert not _beneficiary_exists(first)


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


@pytest.mark.postgres
def test_under_row_security_a_member_chooses_their_beneficiary(pg_api):
    """The member writes only their own row, and the recipient's accounts
    are visible to the payout-account check."""
    organiser, thandi, mother = _person("sipho"), _person(), _person("mother")
    _open_usd_account(mother)
    group = _stokvel(organiser, thandi)
    beneficiary_id = _beneficiary(thandi, mother, CURRENCY_USD)

    response = pg_api.beneficiary(thandi, group.stokvel_id, beneficiary_id)

    assert response.status_code == 200, response.text
    assert _choices(group.stokvel_id) == {
        group.member_id(organiser): (None, None),
        group.member_id(thandi): (beneficiary_id, CURRENCY_USD),
    }


@pytest.mark.postgres
def test_under_row_security_a_member_adds_their_own_missing_row(pg_api):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, rowless=(thandi,))
    beneficiary_id = _beneficiary(thandi, _person("mother"))

    response = pg_api.beneficiary(thandi, group.stokvel_id, beneficiary_id)

    assert response.status_code == 200, response.text
    assert _choices(group.stokvel_id)[group.member_id(thandi)] == (
        beneficiary_id,
        CURRENCY_ZAR,
    )


@pytest.mark.postgres
def test_under_row_security_a_chosen_beneficiary_cannot_be_removed(pg_api):
    """The member's own cycle row is visible to the check, so the delete is
    refused with 409, not the foreign key's 500."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    beneficiary_id = _beneficiary(thandi, _person("mother"))
    assert (
        pg_api.beneficiary(thandi, group.stokvel_id, beneficiary_id).status_code == 200
    )

    _refused(
        pg_api.delete_beneficiary(thandi, beneficiary_id),
        409,
        "beneficiary_in_use_by_stokvel",
    )
    assert _beneficiary_exists(beneficiary_id)


@pytest.mark.postgres
def test_under_row_security_a_former_member_still_cannot_remove_it(pg_api):
    """A member who has left still sees their cycle row, so the check still
    finds it."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    beneficiary_id = _beneficiary(thandi, _person("mother"))
    assert (
        pg_api.beneficiary(thandi, group.stokvel_id, beneficiary_id).status_code == 200
    )
    _leave(group.member_id(thandi))

    _refused(
        pg_api.delete_beneficiary(thandi, beneficiary_id),
        409,
        "beneficiary_in_use_by_stokvel",
    )
