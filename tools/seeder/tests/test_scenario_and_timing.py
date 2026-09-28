from datetime import UTC, date, datetime
from decimal import Decimal
from random import Random

import pytest

from remitx_seeder.rates import HistoricalRateProvider
from remitx_seeder.scenario import Scenario, list_scenarios, load_scenario
from remitx_seeder.stories.kyc import PATH_APPROVE
from remitx_seeder.stories.money import floor_send, round_send, typo
from remitx_seeder.stories.timing import SAST, business_time, paydays


def test_committed_scenarios_load():
    assert {"default", "small"} <= set(list_scenarios())
    assert "loadtest" not in list_scenarios()
    for name in list_scenarios():
        load_scenario(name)


def test_unknown_scenario_keys_are_refused():
    with pytest.raises(ValueError, match="Unknown scenario keys"):
        Scenario.from_dict({"sendrs": 3})
    with pytest.raises(ValueError, match="Unknown kyc keys"):
        Scenario.from_dict({"kyc": {"reject": 0.1}})


def test_rates_must_be_probabilities():
    with pytest.raises(ValueError, match="reject_rate"):
        Scenario.from_dict({"kyc": {"reject_rate": 1.5}})


def test_review_delay_hours_must_be_a_low_high_pair():
    with pytest.raises(ValueError, match="review_delay_hours"):
        Scenario.from_dict({"kyc": {"review_delay_hours": [1, 24, 36, 48]}})
    with pytest.raises(ValueError, match="review_delay_hours"):
        Scenario.from_dict({"kyc": {"review_delay_hours": [72, 2]}})


def test_a_scenario_with_senders_needs_decision_makers():
    with pytest.raises(ValueError, match="compliance_officer"):
        Scenario.from_dict({"staff": {"treasury_operator": 1}})


def test_scenarios_round_trip():
    scenario = Scenario(name="x", days=10, senders=3)
    assert Scenario.from_dict(scenario.as_dict()) == scenario


def test_the_25th_moves_to_the_friday_before_a_weekend():
    # 25 Oct 2026 is a Sunday.
    assert paydays("25th", date(2026, 10, 1), date(2026, 10, 31)) == [
        date(2026, 10, 23)
    ]


def test_month_end_is_the_last_weekday():
    # 31 Oct 2026 is a Saturday.
    assert paydays("month_end", date(2026, 10, 1), date(2026, 10, 31)) == [
        date(2026, 10, 30)
    ]


def test_weekly_paydays_are_fridays():
    days = paydays("weekly_friday", date(2026, 9, 1), date(2026, 9, 30))
    assert days and all(day.weekday() == 4 for day in days)


def test_staff_work_weekday_office_hours_in_sast():
    rng = Random(1)
    saturday_night = datetime(2026, 9, 26, 22, 0, tzinfo=SAST)
    moved = business_time(rng, saturday_night).astimezone(SAST)
    assert moved.weekday() == 0 and 8 <= moved.hour < 17


def test_rates_are_consistent_cross_rates():
    provider = HistoricalRateProvider(1, date(2026, 6, 1), date(2026, 9, 30))
    usd_zar = provider.get_rate("USD", "ZAR")
    zar_usd = provider.get_rate("ZAR", "USD")
    assert abs(usd_zar * zar_usd - 1) < Decimal("0.000001")
    assert provider.get_rate("ZAR", "NAD") == Decimal("1")
    assert Decimal("16.8") <= usd_zar <= Decimal("19.6")


def test_rates_follow_the_replayed_day(monkeypatch):
    import time_machine

    provider = HistoricalRateProvider(1, date(2026, 6, 1), date(2026, 9, 30))
    with time_machine.travel(datetime(2026, 6, 10, 12, tzinfo=UTC)):
        june = provider.get_rate("USD", "ZAR")
    with time_machine.travel(datetime(2026, 9, 10, 12, tzinfo=UTC)):
        september = provider.get_rate("USD", "ZAR")
    assert june == provider.usd_per_unit("ZAR", date(2026, 6, 10)).quantize(
        Decimal("0.00000001")
    )
    assert september == provider.usd_per_unit("ZAR", date(2026, 9, 10)).quantize(
        Decimal("0.00000001")
    )


def test_people_send_round_amounts_within_what_they_have():
    assert round_send(Decimal("873")) == Decimal("850")
    assert round_send(Decimal("1260")) == Decimal("1300")
    assert floor_send(Decimal("1299.99")) == Decimal("1200")
    assert floor_send(Decimal("449")) == Decimal("400")


def test_typos_never_match_the_real_reference():
    class Ctx:
        rng = Random(3)

    for _ in range(100):
        assert typo(Ctx, "tendai1-zar") != "tendai1-zar"


def test_tier_two_edge_case_is_fixed_to_approved_path():
    from remitx_seeder.clerk import FakeClerkGateway
    from remitx_seeder.clock import SimClock
    from remitx_seeder.context import RunContext
    from remitx_seeder.engine import _guarantee_edge_cases, _plan_people

    now = datetime(2026, 9, 28, tzinfo=UTC)
    ctx = RunContext(
        scenario=Scenario(senders=14),
        run_id="run-test",
        clock=SimClock(),
        clerk=FakeClerkGateway(existing_users=0),
        emit=lambda _: None,
        window_start=now,
        window_end=now,
    )
    _plan_people(ctx)
    _guarantee_edge_cases(ctx)

    person = next(
        p
        for p in ctx.people.values()
        if p.persona.extra.get("edge_case") == "tier 2 approval"
    )
    assert person.force_tier_two
    assert person.persona.source_of_wealth
    assert person.kyc_path_fixed
    assert person.kyc_path == PATH_APPROVE
