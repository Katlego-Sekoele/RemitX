"""The stokvel demo (R6-03, #268): one seed run of the committed `demo`
scenario, then the state the demo starts from.

The last two tests start each stokvel's cycle through the real controller, as
the Organiser would on the day: the ready stokvel starts, and starting the
lapse stokvel lapses its pending invitation. They change the data, so they
stay last in the file.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from remitx_seeder.clerk import FakeClerkGateway
from remitx_seeder.context import RunContext
from remitx_seeder.engine import run_seed
from remitx_seeder.scenario import Scenario, load_scenario
from remitx_seeder.storage import MemoryStorage
from remitx_seeder.stories.stokvel import (
    MIN_DEPOSIT_ZAR,
    DemoNotReady,
    StokvelDemoStory,
)
from remitx_seeder.stories.stokvel_plan import (
    DEMO_MEMBERS,
    LAPSE_STOKVEL,
    READY_STOKVEL,
)

ROUNDS = len(DEMO_MEMBERS)


@pytest.fixture(scope="module")
def demo(database):
    events: list[dict] = []
    summary = run_seed(
        load_scenario("demo"),
        clerk=FakeClerkGateway(),
        clerk_enabled=True,
        storage=MemoryStorage(),
        emit=events.append,
    )
    return {"summary": summary, "db": database, "events": events}


@pytest.fixture
def session(demo):
    db = demo["db"]
    token = db.open_session()
    try:
        yield db.session
    finally:
        db.close_session(token)


def _stokvel_id(demo, which: str) -> uuid.UUID:
    return uuid.UUID(demo["summary"]["stokvel_demo"][which]["stokvel_id"])


def _user_id(session, email: str) -> uuid.UUID:
    from remitx_api.models.orm.user import User

    return session.scalar(select(User.id).where(User.email == email))


def _forming_rows(session, stokvel_id):
    from remitx_api.models.orm.stokvel_cycle import StokvelCycle
    from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember

    cycle = session.scalar(
        select(StokvelCycle).where(StokvelCycle.stokvel_id == stokvel_id)
    )
    rows = session.scalars(
        select(StokvelCycleMember).where(StokvelCycleMember.cycle_id == cycle.id)
    ).all()
    return cycle, rows


def test_the_backend_refused_nothing(demo):
    assert demo["summary"]["refusals"] == []


def test_every_business_rule_holds(demo):
    report = demo["summary"]["verify"]
    broken = [f for f in report["findings"] if f["severity"] == "error" and not f["ok"]]
    assert report["ok"], broken


def test_the_summary_names_both_stokvels_and_who_signs_in(demo):
    result = demo["summary"]["stokvel_demo"]
    assert result["contribution_uctusd"] == "2.0"
    assert result["ready"]["name"] == READY_STOKVEL
    assert result["lapse"]["name"] == LAPSE_STOKVEL
    people = [*result["ready"]["payout_order"], result["lapse"]["pending_invitation"]]
    assert [p["role"] for p in result["ready"]["payout_order"]] == [
        "Organiser",
        "second member",
        "third member",
    ]
    assert all(p["can_sign_in"] for p in people)
    assert [p["email"] for p in result["ready"]["payout_order"]] == [
        "stokvel.organiser+clerk_test@example.com",
        "stokvel.member2+clerk_test@example.com",
        "stokvel.member3+clerk_test@example.com",
    ]


def test_every_member_is_kyc_approved_and_funded_for_three_rounds(demo, session):
    from remitx_api.models.orm.account import CURRENCY_ZAR
    from remitx_api.repositories.account_repository import AccountRepository
    from remitx_api.repositories.kyc_application_repository import (
        KycApplicationRepository,
    )

    # The story itself refuses to set up a member short of three rounds at
    # the replayed rate; this checks the deposit landed and was kept.
    accounts = AccountRepository()
    for member in demo["summary"]["stokvel_demo"]["ready"]["payout_order"]:
        user_id = _user_id(session, member["email"])
        assert KycApplicationRepository().get_standing(user_id).is_verified
        zar = accounts.get_user_account(user_id, CURRENCY_ZAR)
        assert accounts.get_available_balance(zar.account_id) >= MIN_DEPOSIT_ZAR


def test_the_demo_money_is_kept(demo):
    counts = demo["summary"]["counts"]
    assert counts["deposits.kept"] == ROUNDS
    assert counts["stokvel_demo.funded"] == ROUNDS


def test_the_ready_stokvel_has_three_members_ordered_with_beneficiaries(demo, session):
    from remitx_api.models.orm.stokvel_cycle import StokvelCycleStatus
    from remitx_api.models.orm.stokvel_invitation import StokvelInvitation

    stokvel_id = _stokvel_id(demo, "ready")
    cycle, rows = _forming_rows(session, stokvel_id)
    assert cycle.status == StokvelCycleStatus.FORMING.value
    assert cycle.registered_at is None
    assert sorted(row.payout_position for row in rows) == [0, 1, 2]
    assert all(row.payout_beneficiary_id and row.payout_currency for row in rows)
    assert not any(row.locked for row in rows)
    # Three different beneficiaries, each paid across a border (in their
    # own country's currency, never rand)
    assert len({row.payout_beneficiary_id for row in rows}) == ROUNDS
    assert "ZAR" not in {row.payout_currency for row in rows}
    statuses = session.scalars(
        select(StokvelInvitation.status).where(
            StokvelInvitation.stokvel_id == stokvel_id
        )
    ).all()
    assert sorted(statuses) == ["accepted", "accepted"]


def test_the_lapse_stokvel_has_two_ready_members_and_one_pending_invitation(
    demo, session
):
    from remitx_api.models.orm.stokvel_invitation import StokvelInvitation

    stokvel_id = _stokvel_id(demo, "lapse")
    _cycle, rows = _forming_rows(session, stokvel_id)
    assert sorted(row.payout_position for row in rows) == [0, 1]
    assert all(row.payout_beneficiary_id for row in rows)
    pending = session.scalars(
        select(StokvelInvitation).where(
            StokvelInvitation.stokvel_id == stokvel_id,
            StokvelInvitation.status == "pending",
        )
    ).all()
    organiser = demo["summary"]["stokvel_demo"]["lapse"]["pending_invitation"]
    assert [i.invitee_user_id for i in pending] == [
        _user_id(session, organiser["email"])
    ]


def _story(contribution: float = 20.0) -> StokvelDemoStory:
    ctx = SimpleNamespace(
        scenario=SimpleNamespace(
            stokvel=SimpleNamespace(contribution_uctusd=contribution)
        )
    )
    members = [SimpleNamespace(key=spec.key) for spec in DEMO_MEMBERS]
    return StokvelDemoStory(ctx, sim=None, money=None, members=members)


def test_members_in_both_stokvels_are_funded_for_both(session):
    """The second and third members pay three rounds in the ready stokvel
    and two in the lapse stokvel, whose fee is split two ways (#348 review
    of this PR): five contributions, not three."""
    from remitx_api.controllers.stokvel_contribution_controller import (
        contribution_fee_share,
    )
    from remitx_api.services.quote_service import TokenRates, token_to_fiat

    rates = TokenRates(
        currency="ZAR",
        units_per_token=Decimal("18.5"),
        token_per_unit=Decimal("0.05405405"),
        zar_token_per_unit=Decimal("0.05405405"),
    )
    story = _story()
    fiat = token_to_fiat(Decimal("20"), rates)

    def round_cost(spec, size: int) -> Decimal:
        fee = max(
            contribution_fee_share(fiat, rates, member_count=size, payout_currency=c)
            for c in spec.corridor["payout_currencies"]
        )
        return (fiat + fee) * size

    organiser, second, third = story.members
    assert story._cost(organiser, rates) == round_cost(DEMO_MEMBERS[0], 3)
    for person, spec in ((second, DEMO_MEMBERS[1]), (third, DEMO_MEMBERS[2])):
        assert story._cost(person, rates) == round_cost(spec, 3) + round_cost(spec, 2)
        assert story._cost(person, rates) >= fiat * 5


def test_a_setup_that_did_not_finish_is_a_refusal():
    ctx = RunContext(
        scenario=Scenario(),
        run_id="test",
        clock=None,
        clerk=None,
        emit=lambda event: None,
        window_start=datetime.now(UTC) - timedelta(days=14),
        window_end=datetime.now(UTC),
    )
    ctx.count("events.stokvel.demo.check")
    story = StokvelDemoStory(
        ctx,
        sim=None,
        money=None,
        members=[SimpleNamespace(key=s.key) for s in DEMO_MEMBERS],
    )

    story.finish()

    assert [r["event"] for r in ctx.refusals] == ["stokvel.demo"]
    assert "events.stokvel.demo.check" in ctx.refusals[0]["message"]


def test_seeding_the_demo_again_without_a_reset_is_refused(demo):
    with pytest.raises(DemoNotReady, match="Reset the target"):
        run_seed(
            load_scenario("demo"),
            clerk=FakeClerkGateway(),
            clerk_enabled=True,
            storage=MemoryStorage(),
            emit=lambda event: None,
        )


def _start(demo, which: str, monkeypatch):
    """Start the stokvel's cycle as its Organiser would, rounds five
    minutes apart from now."""
    from remitx_api.controllers.stokvel_cycle_controller import (
        RoundTimes,
        StokvelCycleController,
    )
    from remitx_api.models.orm.stokvel import Stokvel
    from remitx_api.repositories.stokvel_member_repository import (
        StokvelMemberRepository,
    )
    from remitx_api.services import queue_service

    queued: list[str] = []
    monkeypatch.setattr(queue_service, "enqueue_start_cycle", queued.append)
    db = demo["db"]
    token = db.open_session()
    try:
        stokvel = db.session.get(Stokvel, _stokvel_id(demo, which))
        organiser_id = stokvel.organiser_user_id
        size = len(StokvelMemberRepository().list_active(stokvel.id))
        now = datetime.now(UTC)
        schedule = [
            RoundTimes(
                start_time=now + timedelta(minutes=5 * i),
                deadline=now + timedelta(minutes=5 * i + 3),
                payout_time=now + timedelta(minutes=5 * i + 4),
            )
            for i in range(size)
        ]
        view = StokvelCycleController().start_cycle(organiser_id, stokvel.id, schedule)
    finally:
        db.close_session(token)
    return view, queued


def test_the_ready_stokvel_starts_on_the_day(demo, monkeypatch):
    view, queued = _start(demo, "ready", monkeypatch)
    assert view.status == "active"
    assert view.total_rounds == ROUNDS
    assert view.lapsed_invitations == 0
    assert queued == [str(view.cycle_id)]


def test_starting_the_lapse_stokvel_lapses_its_invitation(demo, monkeypatch):
    view, _queued = _start(demo, "lapse", monkeypatch)
    assert view.total_rounds == 2
    assert view.lapsed_invitations == 1
