"""Continuing or leaving after a cycle (R2-15, #237):
`POST /stokvels/{id}/members/me/continuation`.

Built on the setup route's helpers (test_stokvel_setup_route.py): a stokvel
whose cycle 1 ran and closed, with cycle 2 opened as the worker opens it when
it records `CycleClosed` (`open_next_cycle`). Tests marked `postgres` run the
same route under row-level security (TEST_DATABASE_URL).
"""

# The shared fixtures are imported by name, which pytest needs and ruff
# reads as unused or redefined.
# ruff: noqa: F401, F811

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from remitx_api.controllers.stokvel_cycle_controller import open_next_cycle
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_USD, CURRENCY_ZAR
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from sqlalchemy import select
from tests.test_stokvel_setup_route import (
    USER_HEADER,
    Api,
    Group,
    Person,
    _add_member,
    _beneficiary,
    _choices,
    _continued,
    _in_session,
    _lock_closed_rows,
    _person,
    _refused,
    _stokvel,
    api,
    pg_api,
)
from tests.test_stokvel_start_cycle import _schedule, enqueued


class ContinuationApi(Api):
    def start(self, as_: Person, stokvel_id, rounds):
        return self.client.post(
            f"/stokvels/{stokvel_id}/cycles",
            json={"rounds": rounds},
            headers={USER_HEADER: str(as_.id)},
        )

    def continuation(self, as_: Person, stokvel_id, choice, beneficiary_id=None):
        body = {"choice": choice}
        if beneficiary_id is not None:
            body["beneficiary_id"] = str(beneficiary_id)
        return self.client.post(
            f"/stokvels/{stokvel_id}/members/me/continuation",
            json=body,
            headers={USER_HEADER: str(as_.id)},
        )


@pytest.fixture
def capi(api):
    return ContinuationApi(api.client)


@pytest.fixture
def pg_capi(pg_api):
    return ContinuationApi(pg_api.client)


@dataclass(frozen=True)
class AfterCycle:
    group: Group
    # Each person's beneficiary in the closed cycle 1
    paid: dict[Person, uuid.UUID]


def _after_first_cycle(
    organiser: Person,
    *others: Person,
    next_open=True,
    joined: tuple[Person, ...] = (),
):
    """A stokvel whose cycle 1 ran with `organiser` and `others` and closed,
    and, with `next_open`, cycle 2 opened as the worker opens it. `joined`
    accepted an invitation while cycle 1 ran, so were not in it."""
    group = _stokvel(organiser, *others, cycle=StokvelCycleStatus.CLOSED)
    paid = {
        person: _beneficiary(person, _person("mother"))
        for person in (organiser, *others)
    }
    _lock_closed_rows(group, paid)
    for person in joined:

        def join(person=person):
            stokvel = db.session.get(Stokvel, group.stokvel_id)
            group.member_ids[person] = _add_member(stokvel, person, invited=True)
            db.session.commit()

        _in_session(join)
    if next_open:

        def open_next():
            closed = db.session.scalars(
                select(StokvelCycle).where(StokvelCycle.stokvel_id == group.stokvel_id)
            ).one()
            open_next_cycle(db.session, closed)
            db.session.commit()

        _in_session(open_next)
    return AfterCycle(group, paid)


def _left_at(member_id: uuid.UUID):
    return _in_session(lambda: db.session.get(StokvelMember, member_id).left_at)


def _start_cycle(stokvel_id, number: int) -> None:
    """Mark the stokvel's cycle `number` started, as R2-10 leaves it."""

    def start():
        cycle = db.session.scalars(
            select(StokvelCycle).where(
                StokvelCycle.stokvel_id == stokvel_id,
                StokvelCycle.cycle_number == number,
            )
        ).one()
        cycle.status = StokvelCycleStatus.ACTIVE.value
        cycle.started_at = datetime.now(UTC)
        cycle.total_rounds = 2
        cycle.current_round = 0
        db.session.commit()

    _in_session(start)


# --- continuing ------------------------------------------------------------


def test_continuing_carries_the_beneficiary_over(capi):
    organiser, thandi = _person("sipho"), _person()
    after = _after_first_cycle(organiser, thandi)
    group = after.group

    response = capi.continuation(thandi, group.stokvel_id, "continue")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "stokvel_id": str(group.stokvel_id),
        "cycle_number": 2,
        "member_id": str(group.member_id(thandi)),
        "choice": "continue",
        "beneficiary_id": str(after.paid[thandi]),
        "payout_currency": CURRENCY_ZAR,
    }
    assert _choices(group.stokvel_id) == {
        group.member_id(organiser): (after.paid[organiser], CURRENCY_ZAR),
        group.member_id(thandi): (after.paid[thandi], CURRENCY_ZAR),
    }
    assert _continued(group.stokvel_id, 1)[group.member_id(thandi)] is True


def test_continuing_with_a_new_beneficiary_pays_them_next_cycle(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    new_choice = _beneficiary(thandi, _person("brother"))

    response = capi.continuation(thandi, group.stokvel_id, "continue", new_choice)

    assert response.status_code == 200, response.text
    assert response.json()["beneficiary_id"] == str(new_choice)
    assert _choices(group.stokvel_id)[group.member_id(thandi)] == (
        new_choice,
        CURRENCY_ZAR,
    )


def test_continuing_again_changes_or_keeps_the_choice(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    new_choice = _beneficiary(thandi, _person("brother"))

    capi.continuation(thandi, group.stokvel_id, "continue")
    capi.continuation(thandi, group.stokvel_id, "continue", new_choice)
    response = capi.continuation(thandi, group.stokvel_id, "continue")

    assert response.status_code == 200, response.text
    assert response.json()["beneficiary_id"] == str(new_choice)


def test_choosing_a_beneficiary_for_the_next_cycle_counts_as_continuing(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    new_choice = _beneficiary(thandi, _person("brother"))

    response = capi.beneficiary(thandi, group.stokvel_id, new_choice)

    assert response.status_code == 200, response.text
    assert response.json()["cycle_number"] == 2
    assert _continued(group.stokvel_id, 1)[group.member_id(thandi)] is True
    ordered = capi.payout_order(
        organiser,
        group.stokvel_id,
        [group.member_id(thandi), group.member_id(organiser)],
    )
    assert ordered.status_code == 200, ordered.text


def test_the_organiser_is_continued_already_and_may_change_beneficiary(capi):
    organiser, thandi = _person("sipho"), _person()
    after = _after_first_cycle(organiser, thandi)
    group = after.group
    assert _continued(group.stokvel_id, 1)[group.member_id(organiser)] is True
    new_choice = _beneficiary(organiser, _person("brother"))

    response = capi.continuation(organiser, group.stokvel_id, "continue", new_choice)

    assert response.status_code == 200, response.text
    assert response.json()["beneficiary_id"] == str(new_choice)


# --- leaving ---------------------------------------------------------------


def test_leaving_ends_the_membership(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group

    response = capi.continuation(thandi, group.stokvel_id, "leave")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "stokvel_id": str(group.stokvel_id),
        "cycle_number": 2,
        "member_id": str(group.member_id(thandi)),
        "choice": "leave",
        "beneficiary_id": None,
        "payout_currency": None,
    }
    assert _left_at(group.member_id(thandi)) is not None
    assert _continued(group.stokvel_id, 1)[group.member_id(thandi)] is False
    # Final: a former member is no longer a member to choose again.
    _refused(capi.continuation(thandi, group.stokvel_id, "continue"), 404)


def test_a_member_who_continued_may_still_leave(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    capi.continuation(thandi, group.stokvel_id, "continue")

    response = capi.continuation(thandi, group.stokvel_id, "leave")

    assert response.status_code == 200, response.text
    assert _left_at(group.member_id(thandi)) is not None
    assert _continued(group.stokvel_id, 1)[group.member_id(thandi)] is False


def test_the_organiser_cannot_leave(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group

    _refused(
        capi.continuation(organiser, group.stokvel_id, "leave"),
        409,
        "organiser_cannot_leave",
    )
    assert _left_at(group.member_id(organiser)) is None


# --- refusals --------------------------------------------------------------


def test_there_is_nothing_to_continue_before_a_cycle_has_finished(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)

    _refused(
        capi.continuation(thandi, group.stokvel_id, "continue"),
        409,
        "nothing_to_continue",
    )


def test_the_choice_closes_when_the_next_cycle_starts(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    _start_cycle(group.stokvel_id, 2)

    _refused(capi.continuation(thandi, group.stokvel_id, "leave"), 409, "cycle_locked")


def test_a_member_waits_until_the_next_cycle_is_open(capi):
    """A cycle that closed before the worker opened successors: only the
    Organiser may open the next."""
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi, next_open=False).group

    _refused(
        capi.continuation(thandi, group.stokvel_id, "continue"),
        409,
        "cycle_not_forming",
    )


def test_the_organisers_choice_opens_a_missing_next_cycle(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi, next_open=False).group

    response = capi.continuation(organiser, group.stokvel_id, "continue")

    assert response.status_code == 200, response.text
    assert response.json()["cycle_number"] == 2
    assert capi.continuation(thandi, group.stokvel_id, "continue").status_code == 200


def test_a_deactivated_stokvel_takes_no_choice(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group

    def deactivate():
        db.session.get(Stokvel, group.stokvel_id).deactivated_at = datetime.now(UTC)
        db.session.commit()

    _in_session(deactivate)

    _refused(
        capi.continuation(thandi, group.stokvel_id, "continue"),
        409,
        "stokvel_deactivated",
    )


def test_an_outsider_gets_not_found(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group

    _refused(capi.continuation(_person("outsider"), group.stokvel_id, "leave"), 404)
    _refused(capi.continuation(thandi, uuid.uuid4(), "leave"), 404)


def test_someone_elses_beneficiary_is_not_found(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    theirs = _beneficiary(organiser, _person("brother"))

    _refused(capi.continuation(thandi, group.stokvel_id, "continue", theirs), 404)


def test_a_beneficiary_whose_recipient_has_no_account_in_its_currency(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    abroad = _beneficiary(thandi, _person("cousin"), CURRENCY_USD)

    response = capi.continuation(thandi, group.stokvel_id, "continue", abroad)

    assert response.status_code == 400, response.text


@pytest.mark.parametrize(
    "body",
    [
        {"choice": "pause"},
        {},
        {"choice": "continue", "extra": True},
        {"choice": "leave", "beneficiary_id": str(uuid.uuid4())},
    ],
    ids=["unknown-choice", "no-choice", "unknown-field", "leave-with-beneficiary"],
)
def test_an_invalid_body_is_refused(capi, body):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group

    response = capi.client.post(
        f"/stokvels/{group.stokvel_id}/members/me/continuation",
        json=body,
        headers={USER_HEADER: str(thandi.id)},
    )

    assert response.status_code == 422, response.text


# --- the next cycle's payout order and start --------------------------------


def _member(group: Group, person: Person) -> str:
    return str(group.member_id(person))


def test_the_order_names_only_members_going_into_the_next_cycle(capi):
    organiser, thandi, lerato = _person("sipho"), _person(), _person("lerato")
    group = _after_first_cycle(organiser, thandi, lerato).group
    capi.continuation(thandi, group.stokvel_id, "continue")

    response = capi.payout_order(
        organiser,
        group.stokvel_id,
        [group.member_id(thandi), group.member_id(organiser)],
    )

    assert response.status_code == 200, response.text
    assert response.json()["cycle_number"] == 2
    assert [place["member_id"] for place in response.json()["order"]] == [
        _member(group, thandi),
        _member(group, organiser),
    ]


def test_the_order_cannot_name_a_member_who_has_not_chosen(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group

    response = capi.payout_order(
        organiser,
        group.stokvel_id,
        [group.member_id(organiser), group.member_id(thandi)],
    )

    _refused(response, 422, "invalid_payout_order")
    assert "hasn't chosen to continue" in response.json()["detail"]


def test_the_order_must_name_every_member_who_continued(capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    capi.continuation(thandi, group.stokvel_id, "continue")

    response = capi.payout_order(
        organiser, group.stokvel_id, [group.member_id(organiser)]
    )

    _refused(response, 422, "invalid_payout_order")
    assert "every member continuing" in response.json()["detail"]


def test_someone_who_joined_during_the_cycle_goes_into_the_next(capi):
    organiser, thandi, lerato = _person("sipho"), _person(), _person("lerato")
    group = _after_first_cycle(organiser, thandi, joined=(lerato,)).group
    capi.beneficiary(lerato, group.stokvel_id, _beneficiary(lerato, organiser))

    response = capi.payout_order(
        organiser,
        group.stokvel_id,
        [group.member_id(lerato), group.member_id(organiser)],
    )

    assert response.status_code == 200, response.text


def test_a_second_cycle_starts_with_the_members_who_continued(capi, enqueued):
    """The ticket's "done when": a closed cycle is followed by a second one.
    Thandi continues, Lerato leaves and Musa never chooses, so is treated as
    leaving when it starts."""
    organiser = _person("sipho")
    thandi, lerato, musa = _person(), _person("lerato"), _person("musa")
    after = _after_first_cycle(organiser, thandi, lerato, musa)
    group = after.group
    assert capi.continuation(thandi, group.stokvel_id, "continue").status_code == 200
    assert capi.continuation(lerato, group.stokvel_id, "leave").status_code == 200
    order = [group.member_id(thandi), group.member_id(organiser)]
    assert capi.payout_order(organiser, group.stokvel_id, order).status_code == 200

    response = capi.start(organiser, group.stokvel_id, _schedule(2))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cycle_number"] == 2
    assert body["total_rounds"] == 2
    assert [place["member_id"] for place in body["order"]] == [
        str(member_id) for member_id in order
    ]
    assert [place["beneficiary_id"] for place in body["order"]] == [
        str(after.paid[thandi]),
        str(after.paid[organiser]),
    ]
    assert enqueued == [body["cycle_id"]]
    assert _left_at(group.member_id(musa)) is not None
    assert _left_at(group.member_id(thandi)) is None
    assert _continued(group.stokvel_id, 1) == {
        group.member_id(organiser): True,
        group.member_id(thandi): True,
        group.member_id(lerato): False,
        group.member_id(musa): False,
    }


def test_a_second_cycle_needs_two_members_who_continued(capi, enqueued):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    capi.payout_order(organiser, group.stokvel_id, [group.member_id(organiser)])

    _refused(
        capi.start(organiser, group.stokvel_id, _schedule(1)), 409, "too_few_members"
    )
    assert _left_at(group.member_id(thandi)) is None
    assert enqueued == []


# --- under Postgres row-level security --------------------------------------


@pytest.mark.postgres
def test_under_row_security_a_member_continues(pg_capi):
    """The member inserts their own row in cycle 2 and records the choice on
    their locked row in cycle 1."""
    organiser, thandi = _person("sipho"), _person()
    after = _after_first_cycle(organiser, thandi)
    group = after.group

    response = pg_capi.continuation(thandi, group.stokvel_id, "continue")

    assert response.status_code == 200, response.text
    assert _choices(group.stokvel_id)[group.member_id(thandi)] == (
        after.paid[thandi],
        CURRENCY_ZAR,
    )
    assert _continued(group.stokvel_id, 1)[group.member_id(thandi)] is True


@pytest.mark.postgres
def test_under_row_security_a_member_leaves(pg_capi):
    organiser, thandi = _person("sipho"), _person()
    group = _after_first_cycle(organiser, thandi).group
    pg_capi.continuation(thandi, group.stokvel_id, "continue")

    response = pg_capi.continuation(thandi, group.stokvel_id, "leave")

    assert response.status_code == 200, response.text
    assert _left_at(group.member_id(thandi)) is not None
    assert _continued(group.stokvel_id, 1)[group.member_id(thandi)] is False


@pytest.mark.postgres
def test_under_row_security_starting_the_next_cycle_ends_undecided_members(
    pg_capi, enqueued
):
    """The Organiser ends another member's membership, the one change
    row-level security allows them on it (`V20261022_1000`)."""
    organiser = _person("sipho")
    thandi, musa = _person(), _person("musa")
    group = _after_first_cycle(organiser, thandi, musa).group
    pg_capi.continuation(thandi, group.stokvel_id, "continue")
    pg_capi.payout_order(
        organiser,
        group.stokvel_id,
        [group.member_id(organiser), group.member_id(thandi)],
    )

    response = pg_capi.start(organiser, group.stokvel_id, _schedule(2))

    assert response.status_code == 201, response.text
    assert _left_at(group.member_id(musa)) is not None
    assert _continued(group.stokvel_id, 1)[group.member_id(musa)] is False
