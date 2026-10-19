"""The settlement worker with its chain calls simulated.

Runs what the deployed worker runs (`python -m remitx_worker`: the health
server plus Celery), after replacing the EVM burn's chain calls in
`remitx_worker.evm_service`: `burn_tokens`, `wait_for_receipt`, and
`get_web3`, which raises so nothing can reach an EVM RPC. Every other step of
settlement is the real code: the three tasks, the claims, storing the burn
hash before the send, and the balance updates. The replacement happens
before Celery forks its pool, so every child process inherits it.

The simulated burn hands its hash to `on_signed` and returns at once, like a
real submit. The wait for its receipt takes about as long as a real burn: a
lognormal delay through the median and 95th percentile of QA's real
settlements (qa_burn_timings.sql). run.sh sets LOADTEST_BURN_P50_S / P95_S
from the profile's `burn` section. Its hashes start 10AD ("load"), so they
can never be mistaken for real ones (which start 0x) or for the seeder's
(5EED).
"""

import math
import os
import random
import secrets
import time
from decimal import Decimal

from remitx_worker import evm_service

HASH_PREFIX = "10AD"
# z-score of the 95th percentile of a standard normal distribution.
Z_95 = 1.6449


def _setting(name: str, default: str) -> float:
    # `or`, not a get() default: compose passes an unset knob through as "".
    return float(os.environ.get(name) or default)


# Calibrated from QA's burns while they still ran on the XRP Ledger (see
# qa_burn_timings.sql); recalibrate once QA has real EVM burns. Profiles
# override.
BURN_P50_S = _setting("LOADTEST_BURN_P50_S", "8.61")
BURN_P95_S = _setting("LOADTEST_BURN_P95_S", "10.24")
# Share of burns that fail before they are signed (so nothing is sent). Zero
# by default so the report measures the happy path; raise it to see failures
# under load.
FAILURE_RATE = _setting("LOADTEST_BURN_FAILURE_RATE", "0")

if not 0 < BURN_P50_S <= BURN_P95_S:
    raise ValueError("need 0 < LOADTEST_BURN_P50_S <= LOADTEST_BURN_P95_S")

_MU = math.log(BURN_P50_S)
_SIGMA = (math.log(BURN_P95_S) - _MU) / Z_95
# The OS's randomness, not the module's: every forked pool child would
# otherwise start from the same seed and draw the same delays.
_rng = random.SystemRandom()


def simulated_burn(amount: Decimal, *, on_signed=None, w3=None) -> str:
    """Stand-in for `evm_service.burn_tokens`: hand a synthetic hash to
    `on_signed` and return it, or fail before signing (nothing sent)."""
    if _rng.random() < FAILURE_RATE:
        raise RuntimeError("burn failed before signing (simulated)")
    tx_hash = HASH_PREFIX + secrets.token_hex(30).upper()
    if on_signed is not None:
        on_signed(tx_hash)
    return tx_hash


def simulated_wait_for_receipt(tx_hash: str, timeout: float = 120, w3=None):
    """Stand-in for `evm_service.wait_for_receipt`: block for a testnet-like
    time, then report the burn mined."""
    time.sleep(_rng.lognormvariate(_MU, _SIGMA))
    return {"transactionHash": tx_hash, "status": 1, "blockNumber": 0}


def no_rpc():
    raise RuntimeError("the load test simulates the chain; nothing may reach an RPC")


def main() -> None:
    evm_service.burn_tokens = simulated_burn
    evm_service.wait_for_receipt = simulated_wait_for_receipt
    evm_service.get_web3 = no_rpc

    from remitx_worker.__main__ import main as run_worker

    run_worker()


if __name__ == "__main__":
    main()
