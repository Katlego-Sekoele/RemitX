"""The simulated burn stands in for the real EVM one without reaching a chain."""

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
    worker.slept = []
    monkeypatch.setattr(worker.time, "sleep", worker.slept.append)
    return worker


def test_a_simulated_hash_can_never_be_a_real_or_seeded_one(monkeypatch):
    worker = load(monkeypatch)

    assert re.fullmatch(r"10AD[0-9A-F]{60}", worker.simulated_burn(Decimal("10")))


def test_the_burn_hands_its_hash_over_before_returning_and_does_not_wait(
    monkeypatch,
):
    """Like the real submit: the worker stores the hash before the send, and
    the time is spent waiting for the receipt, not in the burn."""
    worker = load(monkeypatch)
    seen = []

    tx_hash = worker.simulated_burn(Decimal("10"), on_signed=seen.append)

    assert seen == [tx_hash]
    assert worker.slept == []

    receipt = worker.simulated_wait_for_receipt(tx_hash)

    assert receipt["status"] == 1
    assert receipt["transactionHash"] == tx_hash
    assert len(worker.slept) == 1


def test_the_delay_runs_through_the_given_median_and_95th_percentile(monkeypatch):
    worker = load(monkeypatch, LOADTEST_BURN_P50_S="4", LOADTEST_BURN_P95_S="9")

    assert math.exp(worker._MU) == pytest.approx(4)
    assert math.exp(worker._MU + worker.Z_95 * worker._SIGMA) == pytest.approx(9)


def test_a_knob_passed_through_empty_falls_back_to_its_default(monkeypatch):
    """Compose passes an unset pass-through variable as an empty string."""
    worker = load(monkeypatch, LOADTEST_BURN_P50_S="", LOADTEST_BURN_FAILURE_RATE="")

    assert worker.BURN_P50_S == 8.61
    assert worker.FAILURE_RATE == 0


def test_a_failed_burn_raises_before_its_hash_is_handed_over(monkeypatch):
    worker = load(monkeypatch, LOADTEST_BURN_FAILURE_RATE="1")
    seen = []

    with pytest.raises(RuntimeError, match="before signing"):
        worker.simulated_burn(Decimal("10"), on_signed=seen.append)

    assert seen == []


def test_a_95th_percentile_below_the_median_is_refused(monkeypatch):
    with pytest.raises(ValueError):
        load(monkeypatch, LOADTEST_BURN_P50_S="5", LOADTEST_BURN_P95_S="4")


def test_main_swaps_the_chain_calls_then_runs_the_real_worker(monkeypatch):
    """Guards the seam: a rename in remitx_worker breaks this, not a load test
    run on the eve of a report."""
    import remitx_worker.__main__ as real_worker
    from remitx_worker import evm_service

    worker = load(monkeypatch)
    started = []
    monkeypatch.setattr(real_worker, "main", lambda: started.append(True))
    # Restored after the test: main() replaces them for the process.
    for name in ("burn_tokens", "wait_for_receipt", "get_web3"):
        monkeypatch.setattr(evm_service, name, getattr(evm_service, name))

    worker.main()

    assert evm_service.burn_tokens is worker.simulated_burn
    assert evm_service.wait_for_receipt is worker.simulated_wait_for_receipt
    with pytest.raises(RuntimeError, match="nothing may reach an RPC"):
        evm_service.get_web3()
    assert started == [True]
