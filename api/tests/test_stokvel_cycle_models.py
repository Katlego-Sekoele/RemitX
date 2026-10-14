"""Stokvel cycle tables (R2-05): constraints on SQLite, row-level security on
Postgres (the `postgres` lane, TEST_DATABASE_URL)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_USD, CURRENCY_ZAR
from remitx_api.models.orm.beneficiary import Beneficiary, BeneficiaryRelationship
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_invitation import (
    StokvelInvitation,
    StokvelInvitationStatus,
)
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.stokvel_cycle_repository import StokvelCycleRepository
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from tests.kyc_helpers import make_user

_START = datetime(2026, 11, 1, tzinfo=UTC)


def _stokvel(organiser) -> tuple[Stokvel, StokvelMember]:
    stokvel = Stokvel(
        organiser_user_id=organiser.id,
        name="Savings club",
        currency=CURRENCY_ZAR,
        contribution_amount=Decimal("500"),
    )
    db.session.add(stokvel)
    db.session.flush()
    return stokvel, _member(stokvel, organiser)


def _member(stokvel, user, **columns) -> StokvelMember:
    account = AccountRepository().get_or_create_user_account(
        user.id, user.base_reference, stokvel.currency
    )
    member = StokvelMember(
        stokvel_id=stokvel.id, user_id=user.id, account_id=account.account_id, **columns
    )
    db.session.add(member)
    db.session.flush()
    return member


def _cycle(stokvel, number=1, **columns) -> StokvelCycle:
    cycle = StokvelCycle(stokvel_id=stokvel.id, cycle_number=number, **columns)
    db.session.add(cycle)
    db.session.flush()
    return cycle


def _round(cycle, number, **times) -> StokvelRound:
    """Round `number` a week after the previous one: opens, deadline a day
    later, payout two days later."""
    start = _START + timedelta(weeks=number)
    round_ = StokvelRound(
        cycle_id=cycle.id,
        round=number,
        start_time=times.get("start_time", start),
        deadline=times.get("deadline", start + timedelta(days=1)),
        payout_time=times.get("payout_time", start + timedelta(days=2)),
    )
    db.session.add(round_)
    db.session.flush()
    return round_


def _beneficiary(member) -> Beneficiary:
    beneficiary = Beneficiary(
        sender_user_id=member.user_id,
        linked_user_id=make_user().id,
        payout_currency=CURRENCY_USD,
        relationship=BeneficiaryRelationship.PARENT.value,
    )
    db.session.add(beneficiary)
    db.session.flush()
    return beneficiary


def _in_cycle(cycle, member, **columns) -> StokvelCycleMember:
    row = StokvelCycleMember(cycle_id=cycle.id, member_id=member.id, **columns)
    db.session.add(row)
    db.session.flush()
    return row


def _paid_to(member) -> dict:
    """Payout columns for a member whose beneficiary is chosen."""
    return {
        "payout_beneficiary_id": _beneficiary(member).beneficiary_id,
        "payout_currency": CURRENCY_USD,
    }


def _rejected(write) -> None:
    with pytest.raises(IntegrityError):
        write()
    db.session.rollback()


def _started(**columns) -> dict:
    return {
        "status": StokvelCycleStatus.ACTIVE.value,
        "started_at": datetime.now(UTC),
        "round_count": 2,
        **columns,
    }


def test_a_cycle_with_three_members_and_three_rounds(app_context):
    stokvel, organiser = _stokvel(make_user())
    members = [organiser, _member(stokvel, make_user()), _member(stokvel, make_user())]
    cycle = _cycle(stokvel)
    stokvel.current_cycle_id = cycle.id
    # Set up while forming, in reverse so reads must order them
    for position, member in reversed(list(enumerate(members))):
        _in_cycle(cycle, member, payout_position=position, **_paid_to(member))
        _round(cycle, position)

    # Starting the cycle fixes its rounds and locks every member's payout
    cycle.status = StokvelCycleStatus.ACTIVE.value
    cycle.started_at = datetime.now(UTC)
    cycle.round_count = 3
    cycle.current_round = 0
    for row in db.session.scalars(select(StokvelCycleMember)):
        row.locked = True
    db.session.commit()

    repo = StokvelCycleRepository()
    assert db.session.get(Stokvel, stokvel.id).current_cycle_id == cycle.id
    assert repo.open_cycle(stokvel.id).id == cycle.id
    assert [row.member_id for row in repo.members(cycle.id)] == [
        member.id for member in members
    ]
    assert [row.round for row in repo.rounds(cycle.id)] == [0, 1, 2]
    assert all(row.locked for row in repo.members(cycle.id))


def test_members_without_a_payout_position_are_listed_last(app_context):
    stokvel, organiser = _stokvel(make_user())
    later = _member(stokvel, make_user())
    cycle = _cycle(stokvel)
    _in_cycle(cycle, organiser)
    _in_cycle(cycle, later, payout_position=0)

    assert [row.member_id for row in StokvelCycleRepository().members(cycle.id)] == [
        later.id,
        organiser.id,
    ]


def test_two_members_cannot_share_a_payout_position(app_context):
    stokvel, organiser = _stokvel(make_user())
    other = _member(stokvel, make_user())
    cycle = _cycle(stokvel)
    _in_cycle(cycle, organiser, payout_position=0)

    _rejected(lambda: _in_cycle(cycle, other, payout_position=0))


def test_a_member_is_in_a_cycle_once(app_context):
    stokvel, organiser = _stokvel(make_user())
    cycle = _cycle(stokvel)
    _in_cycle(cycle, organiser)

    _rejected(lambda: _in_cycle(cycle, organiser))


def test_a_locked_member_has_a_position_and_a_beneficiary(app_context):
    stokvel, organiser = _stokvel(make_user())
    cycle = _cycle(stokvel)
    paid_to = _paid_to(organiser)

    _rejected(lambda: _in_cycle(cycle, organiser, locked=True, **paid_to))


def test_a_locked_member_needs_a_beneficiary(app_context):
    stokvel, organiser = _stokvel(make_user())
    cycle = _cycle(stokvel)

    _rejected(lambda: _in_cycle(cycle, organiser, payout_position=0, locked=True))


def test_a_beneficiary_is_chosen_with_its_currency(app_context):
    stokvel, organiser = _stokvel(make_user())
    cycle = _cycle(stokvel)
    beneficiary = _beneficiary(organiser)

    _rejected(
        lambda: _in_cycle(
            cycle, organiser, payout_beneficiary_id=beneficiary.beneficiary_id
        )
    )


def test_one_open_cycle_per_stokvel(app_context):
    stokvel, _ = _stokvel(make_user())
    first = _cycle(stokvel, 1)
    db.session.commit()

    _rejected(lambda: _cycle(stokvel, 2))

    first = db.session.get(StokvelCycle, first.id)
    first.status = StokvelCycleStatus.CLOSED.value
    first.started_at = datetime.now(UTC)
    first.closed_at = datetime.now(UTC)
    first.round_count = 2
    second = _cycle(db.session.get(Stokvel, stokvel.id), 2)
    assert StokvelCycleRepository().open_cycle(stokvel.id).id == second.id


def test_cycle_numbers_are_unique_per_stokvel(app_context):
    stokvel, _ = _stokvel(make_user())
    _cycle(
        stokvel,
        1,
        **_started(status=StokvelCycleStatus.CLOSED.value, closed_at=datetime.now(UTC)),
    )

    _rejected(lambda: _cycle(stokvel, 1))


@pytest.mark.parametrize(
    "columns",
    [
        pytest.param({"status": StokvelCycleStatus.ACTIVE.value}, id="not started"),
        pytest.param(_started(round_count=None), id="no round count"),
        pytest.param(_started(round_count=1), id="one round"),
        pytest.param(_started(current_round=2), id="round out of range"),
        pytest.param(
            _started(status=StokvelCycleStatus.CLOSED.value), id="closed, no time"
        ),
        pytest.param({"closed_at": datetime.now(UTC)}, id="forming, closed time"),
        pytest.param({"status": "paused"}, id="unknown status"),
    ],
)
def test_a_cycle_status_matches_its_columns(app_context, columns):
    stokvel, _ = _stokvel(make_user())

    _rejected(lambda: _cycle(stokvel, **columns))


@pytest.mark.parametrize(
    "times",
    [
        pytest.param({"deadline": _START - timedelta(days=1)}, id="deadline first"),
        pytest.param({"payout_time": _START}, id="payout before deadline"),
    ],
)
def test_a_rounds_times_are_in_order(app_context, times):
    stokvel, _ = _stokvel(make_user())
    cycle = _cycle(stokvel)

    _rejected(lambda: _round(cycle, 0, start_time=_START, **times))


def test_a_rounds_times_may_be_equal(app_context):
    stokvel, _ = _stokvel(make_user())
    cycle = _cycle(stokvel)

    _round(cycle, 0, start_time=_START, deadline=_START, payout_time=_START)


@pytest.mark.postgres
def test_rls_helpers_are_security_definer(postgres_app):
    token = db.open_session()
    try:
        functions = db.session.execute(
            text(
                """
                SELECT proname, prosecdef, proconfig
                  FROM pg_proc
                 WHERE proname IN (
                   'stokvel_cycle_is_member',
                   'stokvel_cycle_is_organiser',
                   'stokvel_member_is_user'
                 )
                """
            )
        ).all()

        assert len(functions) == 3
        for name, security_definer, settings in functions:
            assert security_definer, name
            assert settings == ["search_path=pg_catalog, public, pg_temp"], name
    finally:
        db.close_session(token)


@pytest.mark.postgres
def test_row_security_scopes_each_customer(postgres_app):
    token = db.open_session()
    try:
        organiser, member, former, pending, outsider = (make_user() for _ in range(5))
        stokvel, organiser_row = _stokvel(organiser)
        member_row = _member(stokvel, member)
        _member(stokvel, former, left_at=datetime.now(UTC))
        db.session.add(
            StokvelInvitation(
                stokvel_id=stokvel.id,
                invitee_user_id=pending.id,
                invited_by_user_id=organiser.id,
                status=StokvelInvitationStatus.PENDING.value,
            )
        )
        cycle = _cycle(stokvel)
        _in_cycle(cycle, organiser_row, payout_position=0)
        _in_cycle(cycle, member_row, payout_position=1)
        _round(cycle, 0)
        _round(cycle, 1)
        other, outsider_row = _stokvel(outsider)
        _in_cycle(_cycle(other), outsider_row)
        db.session.commit()
        ours = (stokvel.id, other.id)
        cycle_id = cycle.id
        organiser_row_id = organiser_row.id
        member_row_id = member_row.id

        def visible(user, *, admin=False):
            ours_cycles = select(StokvelCycle.id).where(
                StokvelCycle.stokvel_id.in_(ours)
            )
            with bound_row_security_context(user.id, is_admin_route=admin):
                return tuple(
                    len(db.session.scalars(query).all())
                    for query in (
                        ours_cycles,
                        select(StokvelRound).where(
                            StokvelRound.cycle_id.in_(ours_cycles)
                        ),
                        select(StokvelCycleMember).where(
                            StokvelCycleMember.cycle_id.in_(ours_cycles)
                        ),
                    )
                )

        # (cycles, rounds, cycle members) each customer sees
        expected = {
            "organiser": (organiser, (1, 2, 2)),
            "member": (member, (1, 2, 2)),
            "former member": (former, (1, 2, 2)),
            "pending invitee": (pending, (0, 0, 0)),
            "outsider": (outsider, (1, 0, 1)),
        }
        for who, (user, seen) in expected.items():
            assert visible(user) == seen, who
        assert visible(outsider, admin=True) == (2, 2, 3)

        def update(user, sql, **params):
            with bound_row_security_context(user.id, is_admin_route=False):
                db.session.execute(text(sql), params)

        set_continued = (
            "UPDATE stokvel_cycle_members SET continued = true"
            " WHERE cycle_id = :cycle AND member_id = :member"
        )
        # A member changes their own row; the Organiser changes anyone's
        update(member, set_continued, cycle=cycle_id, member=member_row_id)
        update(organiser, set_continued, cycle=cycle_id, member=member_row_id)
        db.session.commit()

        refused = {
            "another member's row": (
                set_continued,
                {"cycle": cycle_id, "member": organiser_row_id},
            ),
            "the cycle": (
                "UPDATE stokvel_cycles SET cycle_number = cycle_number"
                " WHERE id = :cycle",
                {"cycle": cycle_id},
            ),
            "a round": (
                "UPDATE stokvel_rounds SET deadline = deadline WHERE cycle_id = :cycle",
                {"cycle": cycle_id},
            ),
        }
        for sql, params in refused.values():
            with pytest.raises(ProgrammingError, match="row-level security"):
                update(member, sql, **params)
            db.session.rollback()
    finally:
        db.close_session(token)
