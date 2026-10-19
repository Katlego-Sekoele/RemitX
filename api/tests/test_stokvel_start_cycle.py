"""`POST /stokvels/{id}/cycles` (R2-10, #232).

On SQLite, which has no row-level security, except the tests marked
`postgres`, which run the same route under it (TEST_DATABASE_URL). The
people, stokvels and beneficiaries come from the R2-09 tests' helpers, and
the payout order and beneficiaries are set through their routes, as an
Organiser would before starting.

The ticket's two "done when" cases are here: a cycle starts with an
invitation still pending, which then shows `lapsed`; and one member, or a
member without a beneficiary, is refused.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.config import TestConfig
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.services import queue_service
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from tests.test_stokvel_setup_route import (
    USER_HEADER,
    Api,
    Group,
    Person,
    _add_member,
    _beneficiary,
    _in_session,
    _leave,
    _person,
    _refused,
    _stokvel,
)

_START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


class CycleApi(Api):
    def start(self, as_: Person, stokvel_id, rounds):
        return self.client.post(
            f"/stokvels/{stokvel_id}/cycles",
            json={"rounds": rounds},
            headers={USER_HEADER: str(as_.id)},
        )


def _schedule(n: int, *, minutes_apart: int = 10) -> list[dict]:
    """`n` rounds a few minutes apart, as for the demo (brief §7.5)."""
    rounds = []
    for number in range(n):
        start = _START + timedelta(minutes=minutes_apart * number)
        rounds.append(
            {
                "start_time": start.isoformat(),
                "deadline": (start + timedelta(minutes=3)).isoformat(),
                "payout_time": (start + timedelta(minutes=5)).isoformat(),
            }
        )
    return rounds


def _ready(api: CycleApi, *people: Person) -> Group:
    """A stokvel whose members (`people[0]` its Organiser) each have a place
    in the payout order, in that order, and a beneficiary, set through the
    R2-09 routes."""
    organiser, *others = people
    group = _stokvel(organiser, *others)
    order = [group.member_id(person) for person in people]
    assert api.payout_order(organiser, group.stokvel_id, order).status_code == 200
    for person in people:
        _choose(api, group, person)
    return group


def _choose(api: CycleApi, group: Group, person: Person) -> uuid.UUID:
    beneficiary_id = _beneficiary(person, _person("gogo"))
    response = api.beneficiary(person, group.stokvel_id, beneficiary_id)
    assert response.status_code == 200, response.text
    return beneficiary_id


def _pending_invitation(group: Group, invitee: Person) -> uuid.UUID:
    def insert():
        invitation = StokvelInvitation(
            stokvel_id=group.stokvel_id,
            invitee_user_id=invitee.id,
            invited_by_user_id=group.organiser.id,
        )
        db.session.add(invitation)
        db.session.commit()
        return invitation.id

    return _in_session(insert)


def _open_cycle(stokvel_id) -> StokvelCycle:
    def read():
        cycle = db.session.scalars(
            select(StokvelCycle).where(
                StokvelCycle.stokvel_id == stokvel_id,
                StokvelCycle.status != StokvelCycleStatus.CLOSED.value,
            )
        ).one()
        db.session.expunge(cycle)
        return cycle

    return _in_session(read)


def _locked(cycle_id) -> dict[uuid.UUID, bool]:
    return dict(
        _in_session(
            lambda: db.session.execute(
                select(StokvelCycleMember.member_id, StokvelCycleMember.locked).where(
                    StokvelCycleMember.cycle_id == cycle_id
                )
            ).all()
        )
    )


def _rounds(cycle_id) -> list[tuple[int, datetime, datetime, datetime]]:
    def read():
        return [
            (
                row.round,
                row.start_time.replace(tzinfo=UTC),
                row.deadline.replace(tzinfo=UTC),
                row.payout_time.replace(tzinfo=UTC),
            )
            for row in db.session.scalars(
                select(StokvelRound)
                .where(StokvelRound.cycle_id == cycle_id)
                .order_by(StokvelRound.round)
            )
        ]

    return _in_session(read)


def _invitation(invitation_id) -> StokvelInvitation:
    def read():
        row = db.session.get(StokvelInvitation, invitation_id)
        db.session.expunge(row)
        return row

    return _in_session(read)


@pytest.fixture
def enqueued(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(queue_service, "enqueue_start_cycle", calls.append)
    return calls


@pytest.fixture
def api(enqueued):
    with TestClient(create_app(TestConfig)) as client:
        yield CycleApi(client)
        client.app.dependency_overrides.clear()


# --- Starting ------------------------------------------------------------------


def test_the_organiser_starts_a_ready_cycle(api, enqueued):
    organiser, thandi, lerato = _person("sipho"), _person(), _person("lerato")
    group = _ready(api, organiser, thandi, lerato)

    response = api.start(organiser, group.stokvel_id, _schedule(3))

    assert response.status_code == 201, response.text
    body = response.json()
    cycle = _open_cycle(group.stokvel_id)
    assert body["cycle_id"] == str(cycle.id)
    assert (body["status"], body["cycle_number"]) == ("active", 1)
    assert (body["total_rounds"], body["current_round"]) == (3, 0)
    assert body["registered_at"] is None
    assert [place["member_id"] for place in body["order"]] == [
        str(group.member_id(person)) for person in (organiser, thandi, lerato)
    ]
    assert [place["payout_position"] for place in body["order"]] == [0, 1, 2]
    assert [round_["round"] for round_ in body["rounds"]] == [0, 1, 2]
    assert body["lapsed_invitations"] == 0

    assert (cycle.status, cycle.total_rounds, cycle.current_round) == ("active", 3, 0)
    assert cycle.started_at is not None
    assert cycle.registered_at is None and cycle.start_tx_hash is None
    assert set(_locked(cycle.id).values()) == {True}
    assert _rounds(cycle.id)[1] == (
        1,
        _START + timedelta(minutes=10),
        _START + timedelta(minutes=13),
        _START + timedelta(minutes=15),
    )
    assert enqueued == [str(cycle.id)]


def test_a_pending_invitation_lapses_when_the_cycle_starts(api):
    """Done when: a cycle starts with one invitation still pending, and that
    invitation shows `lapsed`."""
    organiser, thandi, late = _person("sipho"), _person(), _person("late")
    group = _ready(api, organiser, thandi)
    invitation_id = _pending_invitation(group, late)

    response = api.start(organiser, group.stokvel_id, _schedule(2))

    assert response.status_code == 201, response.text
    assert response.json()["lapsed_invitations"] == 1
    invitation = _invitation(invitation_id)
    assert invitation.status == StokvelInvitationStatus.LAPSED.value
    assert invitation.status_changed_by_user_id == organiser.id
    assert invitation.status_changed_at is not None
    memberships = _in_session(
        lambda: db.session.scalars(
            select(StokvelMember).where(StokvelMember.user_id == late.id)
        ).all()
    )
    assert memberships == []


def test_a_lapsed_invitation_can_no_longer_be_accepted(api):
    organiser, thandi, late = _person("sipho"), _person(), _person("late")
    group = _ready(api, organiser, thandi)
    invitation_id = _pending_invitation(group, late)
    api.start(organiser, group.stokvel_id, _schedule(2))

    response = api.client.post(
        f"/invitations/{invitation_id}/accept", headers={USER_HEADER: str(late.id)}
    )

    _refused(response, 409, "invitation_not_pending")


def test_one_member_cannot_start_a_cycle(api, enqueued):
    """Done when: one member is refused."""
    organiser = _person("sipho")
    group = _stokvel(organiser)
    assert (
        api.payout_order(
            organiser, group.stokvel_id, [group.member_id(organiser)]
        ).status_code
        == 200
    )
    _choose(api, group, organiser)

    response = api.start(organiser, group.stokvel_id, _schedule(2))

    _refused(response, 409, "too_few_members")
    assert _open_cycle(group.stokvel_id).status == "forming"
    assert enqueued == []


def test_a_member_without_a_beneficiary_is_refused(api, enqueued):
    """Done when: a member without a beneficiary is refused."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi)
    order = [group.member_id(organiser), group.member_id(thandi)]
    assert api.payout_order(organiser, group.stokvel_id, order).status_code == 200
    _choose(api, group, organiser)

    response = api.start(organiser, group.stokvel_id, _schedule(2))

    _refused(response, 409, "cycle_not_ready")
    assert "beneficiary" in response.json()["detail"]
    cycle = _open_cycle(group.stokvel_id)
    assert cycle.status == "forming"
    assert set(_locked(cycle.id).values()) == {False}
    assert enqueued == []


def test_a_member_with_no_place_in_the_order_is_refused(api):
    """An invitee who accepted after the order was set has a row and no
    position."""
    organiser, thandi, late = _person("sipho"), _person(), _person("late")
    group = _ready(api, organiser, thandi)

    def join():
        stokvel = db.session.get(Stokvel, group.stokvel_id)
        member_id = _add_member(stokvel, late, invited=True)
        db.session.add(
            StokvelCycleMember(cycle_id=stokvel.current_cycle_id, member_id=member_id)
        )
        db.session.commit()

    _in_session(join)

    response = api.start(organiser, group.stokvel_id, _schedule(3))

    _refused(response, 409, "cycle_not_ready")
    assert "payout order" in response.json()["detail"]


def test_a_member_who_left_after_the_order_was_set_leaves_a_gap(api):
    """The leaver keeps their position until the next order, so the current
    members' positions are not 0..n-1: round 1 would pay nobody."""
    organiser, thandi, lerato = _person("sipho"), _person(), _person("lerato")
    group = _ready(api, organiser, thandi, lerato)
    _leave(group.member_id(thandi))

    response = api.start(organiser, group.stokvel_id, _schedule(2))

    _refused(response, 409, "cycle_not_ready")
    assert "Set it again" in response.json()["detail"]


def test_once_the_order_is_set_again_a_former_member_stays_unlocked(api):
    organiser, thandi, lerato = _person("sipho"), _person(), _person("lerato")
    group = _ready(api, organiser, thandi, lerato)
    _leave(group.member_id(thandi))
    order = [group.member_id(lerato), group.member_id(organiser)]
    assert api.payout_order(organiser, group.stokvel_id, order).status_code == 200

    response = api.start(organiser, group.stokvel_id, _schedule(2))

    assert response.status_code == 201, response.text
    assert [place["member_id"] for place in response.json()["order"]] == [
        str(member_id) for member_id in order
    ]
    assert _locked(_open_cycle(group.stokvel_id).id) == {
        group.member_id(lerato): True,
        group.member_id(organiser): True,
        group.member_id(thandi): False,
    }


def test_only_the_organiser_can_start_the_cycle(api, enqueued):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)

    response = api.start(thandi, group.stokvel_id, _schedule(2))

    _refused(response, 403, "not_organiser")
    assert "start a cycle" in response.json()["detail"]
    assert enqueued == []


def test_an_outsider_and_an_unknown_stokvel_are_not_found(api):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)

    _refused(api.start(_person("outsider"), group.stokvel_id, _schedule(2)), 404)
    _refused(api.start(organiser, uuid.uuid4(), _schedule(2)), 404)


def test_a_former_member_is_not_found(api):
    organiser, thandi, lerato = _person("sipho"), _person(), _person("lerato")
    group = _ready(api, organiser, thandi, lerato)
    _leave(group.member_id(thandi))

    _refused(api.start(thandi, group.stokvel_id, _schedule(2)), 404)


def test_a_started_cycle_cannot_be_started_again(api, enqueued):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)
    assert api.start(organiser, group.stokvel_id, _schedule(2)).status_code == 201

    _refused(
        api.start(organiser, group.stokvel_id, _schedule(2)), 409, "cycle_in_progress"
    )
    assert len(enqueued) == 1


def test_setup_is_locked_once_the_cycle_starts(api):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)
    api.start(organiser, group.stokvel_id, _schedule(2))
    order = [group.member_id(thandi), group.member_id(organiser)]

    _refused(api.payout_order(organiser, group.stokvel_id, order), 409, "cycle_locked")
    beneficiary_id = _beneficiary(thandi, _person("gogo"))
    _refused(
        api.beneficiary(thandi, group.stokvel_id, beneficiary_id), 409, "cycle_locked"
    )


def test_a_deactivated_stokvel_cannot_start_a_cycle(api):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)

    def deactivate():
        db.session.get(Stokvel, group.stokvel_id).deactivated_at = datetime.now(UTC)
        db.session.commit()

    _in_session(deactivate)

    _refused(
        api.start(organiser, group.stokvel_id, _schedule(2)), 409, "stokvel_deactivated"
    )


def test_with_no_forming_cycle_there_is_nothing_to_start(api):
    """A stokvel from before cycles opened at creation, whose Organiser has
    not set it up yet."""
    organiser, thandi = _person("sipho"), _person()
    group = _stokvel(organiser, thandi, cycle=None)

    _refused(
        api.start(organiser, group.stokvel_id, _schedule(2)), 409, "cycle_not_forming"
    )


def test_more_members_than_the_cap_are_refused(api, monkeypatch):
    organiser, thandi, lerato = _person("sipho"), _person(), _person("lerato")
    group = _ready(api, organiser, thandi, lerato)
    monkeypatch.setenv("MAX_STOKVEL_MEMBERS", "2")

    _refused(
        api.start(organiser, group.stokvel_id, _schedule(3)), 422, "too_many_members"
    )


def test_a_lost_enqueue_is_logged_and_raised(api, monkeypatch, caplog):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)

    def broker_down(cycle_id):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(queue_service, "enqueue_start_cycle", broker_down)

    with caplog.at_level(logging.ERROR), pytest.raises(ConnectionError):
        api.start(organiser, group.stokvel_id, _schedule(2))

    assert "failed to enqueue start_cycle" in caplog.text
    assert _open_cycle(group.stokvel_id).status == "active"


# --- The schedule --------------------------------------------------------------


def _shifted(rounds, index, field, minutes):
    value = datetime.fromisoformat(rounds[index][field]) + timedelta(minutes=minutes)
    rounds[index][field] = value.isoformat()
    return rounds


@pytest.mark.parametrize(
    "rounds, wording",
    [
        pytest.param(_schedule(3), "one round for each of the 2", id="too many rounds"),
        pytest.param(
            _shifted(_schedule(2), 0, "deadline", -10), "Round 1", id="deadline first"
        ),
        pytest.param(
            _shifted(_schedule(2), 1, "payout_time", -3),
            "Round 2",
            id="payout before deadline",
        ),
        pytest.param(
            _shifted(_schedule(2, minutes_apart=0), 1, "start_time", -1),
            "Round 2 can't",
            id="second round starts first",
        ),
        pytest.param(
            _shifted(_schedule(2, minutes_apart=0), 0, "payout_time", 30),
            "Round 2 can't",
            id="second round pays out first",
        ),
    ],
)
def test_a_schedule_the_contract_would_refuse_is_refused(
    api, enqueued, rounds, wording
):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)

    response = api.start(organiser, group.stokvel_id, rounds)

    _refused(response, 422, "invalid_schedule")
    assert wording in response.json()["detail"]
    assert _open_cycle(group.stokvel_id).status == "forming"
    assert enqueued == []


@pytest.mark.parametrize(
    "rounds",
    [
        pytest.param(_schedule(2)[:1], id="fewer than two rounds"),
        pytest.param(
            [{**_schedule(2)[0], "start_time": "2026-11-02T09:00:00"}, _schedule(2)[1]],
            id="time without an offset",
        ),
        pytest.param(
            [{**_schedule(2)[0], "extra": 1}, _schedule(2)[1]], id="unknown field"
        ),
    ],
)
def test_an_invalid_request_body_is_refused(api, rounds):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)

    assert api.start(organiser, group.stokvel_id, rounds).status_code == 422


def test_equal_times_are_allowed(api):
    """As on the contract: start = deadline = payout, and between rounds."""
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)
    moment = _START.isoformat()
    same = {"start_time": moment, "deadline": moment, "payout_time": moment}

    assert api.start(organiser, group.stokvel_id, [same, same]).status_code == 201


def test_times_are_kept_in_utc_to_the_whole_second(api):
    organiser, thandi = _person("sipho"), _person()
    group = _ready(api, organiser, thandi)
    plus_two = timezone(timedelta(hours=2))
    start = datetime(2026, 11, 2, 11, 0, 0, 750_000, tzinfo=plus_two)
    rounds = [
        {
            "start_time": (start + timedelta(minutes=10 * n)).isoformat(),
            "deadline": (start + timedelta(minutes=10 * n + 3)).isoformat(),
            "payout_time": (start + timedelta(minutes=10 * n + 5)).isoformat(),
        }
        for n in range(2)
    ]

    response = api.start(organiser, group.stokvel_id, rounds)

    assert response.status_code == 201, response.text
    assert response.json()["rounds"][0]["start_time"] == "2026-11-02T09:00:00+00:00"
    assert _rounds(_open_cycle(group.stokvel_id).id)[0][1] == _START


# --- Under Postgres row-level security -------------------------------------------


@pytest.fixture
def pg_api(postgres_app, enqueued):
    with TestClient(postgres_app) as client:
        yield CycleApi(client)
        postgres_app.dependency_overrides.clear()


@pytest.mark.postgres
def test_under_row_security_the_organiser_starts_the_cycle(pg_api, enqueued):
    """The Organiser writes the rounds, locks the other members' rows and
    lapses a pending invitation, all on their customer route."""
    organiser, thandi, late = _person("sipho"), _person(), _person("late")
    group = _ready(pg_api, organiser, thandi)
    invitation_id = _pending_invitation(group, late)

    response = pg_api.start(organiser, group.stokvel_id, _schedule(2))

    assert response.status_code == 201, response.text
    cycle = _open_cycle(group.stokvel_id)
    assert cycle.status == "active"
    assert set(_locked(cycle.id).values()) == {True}
    assert len(_rounds(cycle.id)) == 2
    assert _invitation(invitation_id).status == StokvelInvitationStatus.LAPSED.value
    assert enqueued == [str(cycle.id)]


@pytest.mark.postgres
def test_under_row_security_only_the_organiser_records_a_lapse(pg_api):
    """`V20261019_1052` lets the Organiser record `lapsed`, as themselves;
    the invitee still records only `accepted` or `declined`."""
    organiser, thandi, late = _person("sipho"), _person(), _person("late")
    group = _ready(pg_api, organiser, thandi)
    invitation_id = _pending_invitation(group, late)
    lapse = (
        "UPDATE stokvel_invitations SET status = 'lapsed', "
        "status_changed_at = now(), status_changed_by_user_id = :by "
        "WHERE id = :id"
    )

    def as_(user: Person, by: Person):
        with bound_row_security_context(user.id, is_admin_route=False):
            db.session.execute(text(lapse), {"id": invitation_id, "by": by.id})

    def invitee_lapses():
        with pytest.raises(ProgrammingError, match="row-level security"):
            as_(late, late)
        db.session.rollback()
        as_(organiser, organiser)
        db.session.commit()

    _in_session(invitee_lapses)

    invitation = _invitation(invitation_id)
    assert invitation.status == StokvelInvitationStatus.LAPSED.value
    assert invitation.status_changed_by_user_id == organiser.id
