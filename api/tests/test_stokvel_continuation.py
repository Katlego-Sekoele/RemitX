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


class ContinuationApi(Api):
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


def _after_first_cycle(organiser: Person, *others: Person, next_open=True):
    """A stokvel whose cycle 1 ran with `organiser` and `others` and closed,
    and, with `next_open`, cycle 2 opened as the worker opens it."""
    group = _stokvel(organiser, *others, cycle=StokvelCycleStatus.CLOSED)
    paid = {
        person: _beneficiary(person, _person("mother"))
        for person in (organiser, *others)
    }
    _lock_closed_rows(group, paid)
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
