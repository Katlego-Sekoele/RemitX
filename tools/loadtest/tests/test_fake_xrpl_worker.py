"""The simulated burn stands in for the real one without reaching the XRPL."""

import importlib
import math
import re
from decimal import Decimal

import pytest

KNOBS = ("LOADTEST_BURN_P50_S", "LOADTEST_BURN_P95_S", "LOADTEST_BURN_FAILURE_RATE")


def load(monkeypatch, **env):
    """Import fake_xrpl_worker afresh under exactly these knobs."""
    for name in KNOBS:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    import fake_xrpl_worker

    worker = importlib.reload(fake_xrpl_worker)
    monkeypatch.setattr(worker.time, "sleep", lambda seconds: None)
    return worker


def test_a_simulated_hash_can_never_be_a_real_or_seeded_one(monkeypatch):
    worker = load(monkeypatch)

    assert re.fullmatch(r"10AD[0-9A-F]{60}", worker.simulated_burn(Decimal("10")))


def test_the_delay_runs_through_the_given_median_and_95th_percentile(monkeypatch):
    worker = load(monkeypatch, LOADTEST_BURN_P50_S="4", LOADTEST_BURN_P95_S="9")

    assert math.exp(worker._MU) == pytest.approx(4)
    assert math.exp(worker._MU + worker.Z_95 * worker._SIGMA) == pytest.approx(9)


def test_a_knob_passed_through_empty_falls_back_to_its_default(monkeypatch):
    """Compose passes an unset pass-through variable as an empty string."""
    worker = load(monkeypatch, LOADTEST_BURN_P50_S="", LOADTEST_BURN_FAILURE_RATE="")

    assert worker.BURN_P50_S == 4.0
    assert worker.FAILURE_RATE == 0


def test_a_failed_burn_raises_like_a_rejected_payment(monkeypatch):
    worker = load(monkeypatch, LOADTEST_BURN_FAILURE_RATE="1")

    with pytest.raises(RuntimeError, match="burn Payment failed"):
        worker.simulated_burn(Decimal("10"))


def test_a_95th_percentile_below_the_median_is_refused(monkeypatch):
    with pytest.raises(ValueError):
        load(monkeypatch, LOADTEST_BURN_P50_S="5", LOADTEST_BURN_P95_S="4")


def test_main_swaps_the_burn_then_runs_the_real_worker(monkeypatch):
    """Guards the seam: a rename in remitx_worker breaks this, not a load test
    run on the eve of a report."""
    import remitx_worker.__main__ as real_worker
    from remitx_worker import xrpl_service

    worker = load(monkeypatch)
    started = []
    monkeypatch.setattr(real_worker, "main", lambda: started.append(True))
    monkeypatch.setattr(xrpl_service, "burn_tokens", xrpl_service.burn_tokens)

    worker.main()

    assert xrpl_service.burn_tokens is worker.simulated_burn
    assert started == [True]
